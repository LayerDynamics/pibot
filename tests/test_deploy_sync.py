"""T5.1 — ``pibot deploy`` payload sync: rsync argv, host-only excludes, change diff, dry-run.

The deployable is the installable package (``pibot/`` + ``agent/`` + ``pyproject.toml`` +
the Pi ``requirements.txt``); host-only tooling (``tools/``, ``tests/``, ``docs/``,
``firmware/``, caches, ``.git/``) is excluded. We never surgically strip host-only modules
*out of* the ``pibot`` package — that would break ``agent``'s import web.
"""

from __future__ import annotations

import pibot.deploy.sync as sync


def test_excludes_loaded_from_deployignore() -> None:
    excludes = sync.load_excludes()
    # host-only tooling is excluded ...
    for pat in ("tools/", "tests/", "docs/", "firmware/", ".git/"):
        assert pat in excludes
    # ... but the deployable package is NOT (agent imports transitively from pibot/)
    assert "pibot/" not in excludes
    assert "agent/" not in excludes


def test_rsync_argv_includes_payload_and_excludes_host_tooling() -> None:
    argv = sync.build_rsync_argv(
        "/src/", "pi@host:/opt/pibot/releases/20260611T200318Z/", excludes=sync.load_excludes()
    )
    assert argv[0] == "rsync"
    assert "/src/" in argv
    assert "pi@host:/opt/pibot/releases/20260611T200318Z/" in argv
    # each host-only pattern appears as an --exclude value
    for pat in ("tools/", "tests/", "docs/", "firmware/", ".git/"):
        assert pat in argv
    # the deployable package is never excluded
    assert "pibot/" not in argv
    assert "agent/" not in argv
    # itemized changes requested, and we mirror deletions into the release dir
    assert "-i" in argv
    assert "--delete" in argv


def test_dry_run_sets_rsync_n_flag() -> None:
    argv = sync.build_rsync_argv("/src/", "pi@host:/dst/", excludes=[], dry_run=True)
    assert "-n" in argv  # rsync dry-run: compute the diff, write nothing


def test_not_dry_run_omits_n_flag() -> None:
    argv = sync.build_rsync_argv("/src/", "pi@host:/dst/", excludes=[], dry_run=False)
    assert "-n" not in argv


def test_identity_threads_into_ssh_transport() -> None:
    argv = sync.build_rsync_argv("/src/", "pi@host:/dst/", excludes=[], identity="/k/id")
    transport = argv[argv.index("-e") + 1]
    assert "-i /k/id" in transport


def test_parse_changes_reports_transferred_and_deleted_only() -> None:
    out = (
        ">f+++++++++ agent/app.py\n"
        ".d..t...... agent/\n"  # metadata-only dir entry -> not a content change
        ">f.st...... pibot/config.py\n"
        "*deleting pibot/old.py\n"
        "\n"  # blank lines ignored
    )
    changed = sync.parse_changes(out)
    assert changed == ["agent/app.py", "pibot/config.py", "pibot/old.py"]
    assert "agent/" not in changed


def test_new_release_name_is_sortable_timestamp() -> None:
    a = sync.new_release_name()
    assert a.endswith("Z") and "T" in a and len(a) >= 15  # e.g. 20260611T200318Z


def test_remote_release_dir_and_activate_command() -> None:
    rel = sync.remote_release_dir("/opt/pibot", "20260611T200318Z")
    assert rel == "/opt/pibot/releases/20260611T200318Z"
    cmd = sync.activate_command("/opt/pibot", "20260611T200318Z")
    # atomic symlink swap: write a temp link then rename it over ``current``
    assert "ln -sfn" in cmd and "/opt/pibot/current" in cmd
    assert "releases/20260611T200318Z" in cmd


def test_deploy_runs_rsync_then_activates(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_capture(argv, **kw):
        calls.append(list(argv))
        from pibot.connection.runner import RunResult

        if argv[0] == "rsync":
            return RunResult(0, ">f+++++++++ agent/app.py\n", "", 0.01)
        return RunResult(0, "", "", 0.01)  # mkdir / activate over ssh

    monkeypatch.setattr(sync.runner, "run_capture", fake_capture)
    result = sync.deploy(
        "pi@host", src_root="/src/", remote_base="/opt/pibot", identity=None, dry_run=False
    )
    assert result.changed == ["agent/app.py"]
    assert result.release.startswith("/opt/pibot/releases/")
    kinds = [c[0] for c in calls]
    assert "rsync" in kinds
    # a dry run never activates (no symlink swap)
    calls.clear()
    sync.deploy("pi@host", src_root="/src/", remote_base="/opt/pibot", dry_run=True)
    assert not any("ln -sfn" in " ".join(c) for c in calls)
