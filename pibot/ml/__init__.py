"""On-robot autonomy / VLA-client stack (SPEC-2).

Everything here depends on the optional ``pibot[ml]`` extra (openpi-client, numpy<2.0,
opencv). Nothing in the core CLI/agent imports this package — it is loaded lazily on the
robot only, so the ``numpy<2.0`` pin can never destabilize the stdlib-light suite
(SPEC-2 FR-8; guarded by tests/test_ml_isolation.py). Keep this ``__init__`` import-free.
"""
