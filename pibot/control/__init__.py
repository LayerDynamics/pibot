"""Robot control: safety primitives and the one-shot command path.

The safety primitives here (clamp, latched e-stop, deadman watchdog) are the shared
contract enforced by the agent (M4) and mirrored independently in firmware (M3 T3.5) —
no motion command reaches an actuator without passing them.
"""

from __future__ import annotations
