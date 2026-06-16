"""M-ARM-3 task 3.1 — in-tree kinematic model (`pibot/arm/geometry/`).

The 6-DOF URDF is **generated from the sizing config** (no vendored donor file; the AR3 6R
joint-axis convention is credited in the package README). These tests prove the model loads, has the
expected joint count, and that ``load()`` round-trips the limits/lengths of the config it was
generated from — i.e. the geometry mirrors the (sizing) config, the single source of truth. Pure
stdlib: ``pibot.arm.geometry`` must import without numpy (FK via ikpy lives in M-ARM-3 task 3.2).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from pibot.arm.geometry import JointGeom, default_joints, generate_urdf, load


def test_default_model_loads_with_six_joints() -> None:
    model = load()
    assert Path(model.urdf_path).exists()
    assert len(model.joints) == 6


def test_loaded_model_round_trips_the_generating_config() -> None:
    # The committed pibot_arm.urdf is generate_urdf(default_joints()); load() must recover it.
    src = default_joints()
    model = load()
    assert [j.name for j in model.joints] == [j.name for j in src]
    for got, want in zip(model.joints, src, strict=True):
        assert got.axis == want.axis
        assert got.min_deg == pytest.approx(want.min_deg)
        assert got.max_deg == pytest.approx(want.max_deg)
        assert got.length_m == pytest.approx(want.length_m)


def test_generate_urdf_is_valid_xml_with_one_revolute_joint_each() -> None:
    xml = generate_urdf(default_joints(), name="pibot_arm")
    root = ET.fromstring(xml)
    assert root.tag == "robot"
    assert root.get("name") == "pibot_arm"
    revolute = [j for j in root.iter("joint") if j.get("type") == "revolute"]
    assert len(revolute) == 6
    # Every revolute joint carries an axis and degree-derived radian limits.
    for j in revolute:
        assert j.find("axis") is not None
        limit = j.find("limit")
        assert limit is not None and limit.get("lower") is not None


def test_load_accepts_a_custom_urdf(tmp_path: Path) -> None:
    js = [
        JointGeom("j0", (0.0, 0.0, 1.0), 0.10, -90.0, 90.0),
        JointGeom("j1", (0.0, 1.0, 0.0), 0.20, -45.0, 45.0),
    ]
    p = tmp_path / "two.urdf"
    p.write_text(generate_urdf(js, name="two"))
    model = load(p)
    assert len(model.joints) == 2
    assert model.joints[1].length_m == pytest.approx(0.20)
    assert model.joints[1].max_deg == pytest.approx(45.0)
    assert model.joints[0].axis == (0.0, 0.0, 1.0)


def test_default_joints_match_the_configured_arm_joint_limits_shape() -> None:
    # Geometry limits mirror the per-joint config (sizing is the single source); a 6R arm has six
    # [min,max] pairs that a matching arm_joint_limits config would also carry.
    js = default_joints()
    assert len(js) == 6
    assert all(j.min_deg < j.max_deg for j in js)
