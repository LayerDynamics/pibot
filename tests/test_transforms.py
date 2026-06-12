"""T9.3 — server-side PibotInputs/PibotOutputs transforms (PiBot obs/action <-> model).

PibotInputs packs a PiBot observation into the model's input dict; PibotOutputs slices the
model's wide action chunk down to PiBot's `[v, ω]` (action_dim=2, OQ-2). The slicing works
on both numpy arrays and nested lists, so it's unit-tested without numpy.
"""

from __future__ import annotations

from pibot.ml.transforms import ACTION_DIM, PibotInputs, PibotOutputs


def test_action_dim_is_two_per_oq2() -> None:
    assert ACTION_DIM == 2


def test_pibot_inputs_packs_image_state_prompt() -> None:
    out = PibotInputs()({"image": {"base_0_rgb": "IMG"}, "state": [0.5, 0.0], "prompt": "drive"})
    assert out["image"] == {"base_0_rgb": "IMG"}
    assert out["state"] == [0.5, 0.0]
    assert out["prompt"] == "drive"


def test_pibot_outputs_slices_wide_action_to_v_w() -> None:
    chunk = [[0.5, 0.0, 9.0, 9.0, 9.0], [0.6, 0.1, 9.0, 9.0, 9.0]]  # model emits 32-wide; we want 2
    out = PibotOutputs()({"actions": chunk})
    assert out["actions"] == [[0.5, 0.0], [0.6, 0.1]]


def test_pibot_outputs_slices_numpy_like_array() -> None:
    class _Arr:
        shape = (50, 32)

        def __getitem__(self, idx: object) -> str:
            assert idx == (slice(None), slice(None, 2))  # columns 0:2
            return "SLICED[:, :2]"

    out = PibotOutputs()({"actions": _Arr()})
    assert out["actions"] == "SLICED[:, :2]"


def test_round_trip_obs_to_action_shapes() -> None:
    model_in = PibotInputs()({"image": {"base_0_rgb": "IMG"}, "state": [0.1, 0.2], "prompt": "p"})
    assert set(model_in) >= {"image", "state", "prompt"}
    # identity "model" echoes a wide chunk; outputs must be width-2 rows
    sliced = PibotOutputs()({"actions": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]})
    assert all(len(row) == ACTION_DIM for row in sliced["actions"])
