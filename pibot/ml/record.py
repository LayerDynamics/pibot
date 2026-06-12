"""Demonstration recording (SPEC-2 / M9 T9.5).

During teleop, each step captures the current observation (camera + state + prompt) and
logs it alongside the human's action into the :class:`EpisodeLogger` — the demonstrations
the policy is fine-tuned on (M10). :func:`record_demo_step` is the pure, testable unit;
:func:`run_record` drives a teleop session and writes the LeRobot dataset on the robot.
"""

from __future__ import annotations

from typing import Any

from pibot.ml.episode_logger import EpisodeLogger
from pibot.ml.pibot_environment import PibotEnvironment


def record_demo_step(env: PibotEnvironment, logger: EpisodeLogger, action_vec: list[float]) -> None:
    """Capture the env's current observation and log it with the teleop ``action_vec``."""
    obs = env.get_observation()
    logger.on_step(obs, {"actions": list(action_vec)})


def run_record(  # pragma: no cover - interactive teleop + lerobot write (hardware)
    cfg: Any, camera: Any, prompt: str, out: str
) -> int:
    """Teleop-record a demonstration episode and write it to a LeRobot dataset."""
    from pibot.control.teleop import key_to_action, stdin_key_source
    from pibot.ml.dataset import write_dataset
    from pibot.ml.state import VelocityState

    velocity = VelocityState()  # state = the last teleop velocity (OQ-2)
    env = PibotEnvironment(camera, velocity.vector, prompt)
    logger = EpisodeLogger()
    logger.start_episode(prompt)
    keys = stdin_key_source()
    try:
        while True:
            action = key_to_action(keys())
            if action.kind == "quit":
                break
            if action.kind == "drive":
                # record with the prior velocity as state, then advance the velocity.
                record_demo_step(env, logger, [action.v, action.w])
                velocity.update([action.v, action.w])
    finally:
        keys.restore()  # type: ignore[attr-defined]
        logger.end_episode()
    write_dataset(logger.episodes(), out, repo_id=f"pibot-{prompt}".replace(" ", "-"))
    return 0
