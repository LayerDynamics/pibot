"""Quick smoke test: the Mission Control sidecar app builds without error.

Run from the repo root with the project venv: ``.venv/bin/python .hermes/test_smoke.py``.
Exits non-zero (unhandled exception) if ``create_mc_app`` cannot construct the app.
"""

from aiohttp import web

from pibot.mc.app import create_mc_app

app = create_mc_app(token="smoke")
assert isinstance(app, web.Application)
print("create_mc_app() OK:", type(app))
