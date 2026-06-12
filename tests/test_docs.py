"""T6.3 / T6.7 — doc-lint: runbooks exist, end in a real verification step, and every
markdown doc has language-tagged code blocks and resolvable relative links.

A runbook that can't be verified is a story, not a procedure — so each one must end with a
``## Verify`` step containing a command. The lint (tagged fences, resolving links) keeps
the docs trustworthy and copy-pasteable.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
RUNBOOKS_DIR = REPO / "docs" / "runbooks"
RUNBOOKS = [
    "flash.md",
    "eeprom-recovery.md",
    "e-stop.md",
    "first-boot.md",
    "wireless-bringup.md",
    "nebula-overlay.md",
]

# Every markdown doc we own and lint (runbooks + top-level user docs).
LINTED = [RUNBOOKS_DIR / name for name in RUNBOOKS] + [
    REPO / "README.md",
    REPO / "docs" / "usage.md",
    REPO / "docs" / "hardware-e2e-signoff.md",
]


@pytest.mark.parametrize("name", RUNBOOKS)
def test_runbook_exists(name: str) -> None:
    assert (RUNBOOKS_DIR / name).is_file(), f"missing runbook docs/runbooks/{name}"


@pytest.mark.parametrize("name", RUNBOOKS)
def test_runbook_ends_with_a_verification_step(name: str) -> None:
    text = (RUNBOOKS_DIR / name).read_text(encoding="utf-8")
    assert re.search(r"^##+\s+Verify", text, re.MULTILINE), f"{name} has no '## Verify' section"
    # the verify section must contain a fenced command block
    verify = text[re.search(r"^##+\s+Verify", text, re.MULTILINE).start() :]
    assert "```" in verify, f"{name} verification step has no command block"


def _docs_to_lint() -> list[Path]:
    return [p for p in LINTED if p.is_file()]


def test_some_docs_present_to_lint() -> None:
    assert _docs_to_lint(), "no docs found to lint"


def test_all_code_fences_are_language_tagged() -> None:
    untagged: list[str] = []
    for doc in _docs_to_lint():
        in_block = False
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("```"):
                if not in_block:  # opening fence -> must name a language
                    if len(stripped) <= 3:
                        untagged.append(f"{doc.relative_to(REPO)}:{lineno}")
                    in_block = True
                else:
                    in_block = False
    assert not untagged, f"untagged code fences: {untagged}"


def test_relative_links_resolve() -> None:
    link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    broken: list[str] = []
    for doc in _docs_to_lint():
        for target in link_re.findall(doc.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            path = (doc.parent / target.split("#", 1)[0]).resolve()
            if not path.exists():
                broken.append(f"{doc.relative_to(REPO)} -> {target}")
    assert not broken, f"broken relative links: {broken}"
