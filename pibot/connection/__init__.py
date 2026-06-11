"""Connection layer — SSH/scp/rsync operations against the robot.

Command construction (``sshcmd``) is kept pure and separate from execution
(``runner``) so the argv surface — the part that, if wrong, talks to the wrong host
or mangles a remote command — is exhaustively unit-testable without a network.
"""

from __future__ import annotations
