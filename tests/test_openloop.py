"""T8.4 — the open-loop environment: record (obs, action), NEVER actuate.

The hard gate before any closed-loop motion (SPEC-2 FR-11). The proof is structural: the
open-loop environment holds NO transport, so ``apply_action`` physically cannot send a
drive frame — it only records the (obs, action) pair for the dataset (M9). The openpi
Runtime/broker/policy wiring is built lazily on the robot.
"""

from __future__ import annotations

from pibot.ml.openloop import OpenLoopEnvironment


class _FakeCamera:
    def capture(self) -> str:
        return "IMG"


def test_open_loop_records_pairs_and_returns_none() -> None:
    pairs: list[tuple] = []
    env = OpenLoopEnvironment(
        _FakeCamera(),
        state_fn=lambda: [0.0],
        prompt="drive",
        on_step=lambda o, a: pairs.append((o, a)),
    )
    for i in range(20):
        env.get_observation()
        result = env.apply_action({"actions": [[float(i), 0.0]]})
        assert result is None  # no ACK, no return — it just logs
    assert len(pairs) == 20
    assert pairs[0][0]["prompt"] == "drive"  # the obs that produced the action
    assert pairs[5][1] == {"actions": [[5.0, 0.0]]}


def test_open_loop_env_has_no_transport_so_cannot_actuate() -> None:
    env = OpenLoopEnvironment(_FakeCamera(), lambda: [], "")
    # Structural guarantee: no transport/send anywhere on the open-loop env.
    assert not any("transport" in name or "send" in name for name in vars(env))
    # apply_action without a sink is still a safe no-op (never raises, never actuates).
    assert env.apply_action({"actions": [[1.0]]}) is None


def test_apply_action_without_prior_observation_logs_none_obs() -> None:
    seen: list[tuple] = []
    env = OpenLoopEnvironment(
        _FakeCamera(), lambda: [], "p", on_step=lambda o, a: seen.append((o, a))
    )
    env.apply_action({"actions": [[0.0]]})  # no get_observation() first
    assert seen == [(None, {"actions": [[0.0]]})]
