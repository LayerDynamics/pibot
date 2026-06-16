"""In-tree kinematic model for the PiBot arm (M-ARM-3, SPEC-4 FR-9).

The 6-DOF URDF is **generated from the sizing config** rather than a vendored donor file — one
source of truth (the arm description in :mod:`pibot.arm.sizing`) drives the firmware ``JCFG``, the
sizing calculator, and this model (SPEC R3 anti-drift). The 6-revolute joint-axis convention follows
the **MIT-licensed AR3** arm (credited in ``README.md``); link lengths + joint limits come from
config and are ``⬜ TUNE`` placeholders until the built arm is measured.

Pure stdlib (``xml.etree``) — **no numpy at import**, so the ``pibot.arm`` core / CLI / agent stay
stdlib-light (NFR-2). Forward kinematics (which loads this URDF into an ikpy chain) lives in
:mod:`pibot.arm.kinematics` behind the lazy ``[arm-ik]`` extra.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

_URDF_NAME = "pibot_arm.urdf"
_LINK_RADIUS_M = 0.02  # primitive cylinder collision/visual radius (no meshes vendored)

# The 6R joint-axis convention of the AR3 arm (MIT; see README): base yaw, shoulder/elbow pitch,
# wrist roll, wrist pitch, tool roll. Each link extends along its local +Z to the next joint.
STANDARD_6R_AXES: tuple[tuple[float, float, float], ...] = (
    (0.0, 0.0, 1.0),  # J0 base   — yaw   (sizing "vertical": no gravity torque)
    (0.0, 1.0, 0.0),  # J1 shoulder — pitch
    (0.0, 1.0, 0.0),  # J2 elbow    — pitch
    (1.0, 0.0, 0.0),  # J3 wrist roll
    (0.0, 1.0, 0.0),  # J4 wrist pitch
    (1.0, 0.0, 0.0),  # J5 tool roll
)


@dataclass(frozen=True)
class JointGeom:
    """One revolute joint: rotation ``axis`` (unit xyz), the ``length_m`` of the link reaching to
    the next joint, and the ``[min_deg, max_deg]`` travel limit."""

    name: str
    axis: tuple[float, float, float]
    length_m: float
    min_deg: float
    max_deg: float


@dataclass(frozen=True)
class Model:
    """A loaded kinematic model: the URDF file path (for ikpy) + parsed joint metadata."""

    urdf_path: Path
    joints: list[JointGeom]


def default_joints() -> list[JointGeom]:
    """The default 6-DOF PiBot arm — AR3 6R axes + ``⬜ TUNE`` link lengths/limits (m, deg).

    These mirror a default sizing arm; regenerate the URDF from real dimensions via
    :func:`pibot.arm.sizing.emit_urdf` once the built arm is measured.
    """
    names = ("base", "shoulder", "elbow", "wrist_roll", "wrist_pitch", "tool_roll")
    lengths_m = (0.10, 0.18, 0.16, 0.06, 0.06, 0.08)  # ⬜ TUNE
    limits_deg = (  # ⬜ TUNE — per-joint [min, max]
        (-180.0, 180.0),
        (-90.0, 90.0),
        (-135.0, 135.0),
        (-180.0, 180.0),
        (-90.0, 90.0),
        (-180.0, 180.0),
    )
    return [
        JointGeom(name, STANDARD_6R_AXES[i], lengths_m[i], limits_deg[i][0], limits_deg[i][1])
        for i, name in enumerate(names)
    ]


def _axis_str(axis: tuple[float, float, float]) -> str:
    return f"{axis[0]:g} {axis[1]:g} {axis[2]:g}"


def generate_urdf(joints: list[JointGeom], *, name: str = "pibot_arm") -> str:
    """Generate a valid serial-chain URDF (stdlib XML) for ``joints``: ``base_link`` → one revolute
    joint per :class:`JointGeom` (each link a primitive cylinder along +Z) → a fixed ``tool0`` tip.
    The angle limits are emitted in radians (URDF convention)."""
    robot = ET.Element("robot", {"name": name})
    ET.SubElement(robot, "link", {"name": "base_link"})

    prev_link = "base_link"
    prev_length = 0.0  # the offset from the previous joint to this one (previous link's length)
    for i, jg in enumerate(joints):
        link_name = f"link_{i}"
        joint = ET.SubElement(robot, "joint", {"name": jg.name, "type": "revolute"})
        ET.SubElement(joint, "parent", {"link": prev_link})
        ET.SubElement(joint, "child", {"link": link_name})
        ET.SubElement(joint, "origin", {"xyz": f"0 0 {prev_length:g}", "rpy": "0 0 0"})
        ET.SubElement(joint, "axis", {"xyz": _axis_str(jg.axis)})
        ET.SubElement(
            joint,
            "limit",
            {
                "lower": f"{math.radians(jg.min_deg):.6f}",
                "upper": f"{math.radians(jg.max_deg):.6f}",
                "effort": "10",
                "velocity": "3.14",
            },
        )
        # The link: a primitive cylinder along +Z, centred at length/2, plus a token inertial.
        link = ET.SubElement(robot, "link", {"name": link_name})
        visual = ET.SubElement(link, "visual")
        ET.SubElement(visual, "origin", {"xyz": f"0 0 {jg.length_m / 2:g}", "rpy": "0 0 0"})
        geom = ET.SubElement(visual, "geometry")
        ET.SubElement(
            geom, "cylinder", {"length": f"{jg.length_m:g}", "radius": f"{_LINK_RADIUS_M:g}"}
        )
        inertial = ET.SubElement(link, "inertial")
        ET.SubElement(inertial, "mass", {"value": "0.1"})
        ET.SubElement(
            inertial,
            "inertia",
            {"ixx": "1e-3", "ixy": "0", "ixz": "0", "iyy": "1e-3", "iyz": "0", "izz": "1e-3"},
        )
        prev_link = link_name
        prev_length = jg.length_m

    # Fixed tool tip at the end of the last link — its origin carries the last link's length.
    tool = ET.SubElement(robot, "joint", {"name": "tool", "type": "fixed"})
    ET.SubElement(tool, "parent", {"link": prev_link})
    ET.SubElement(tool, "child", {"link": "tool0"})
    ET.SubElement(tool, "origin", {"xyz": f"0 0 {prev_length:g}", "rpy": "0 0 0"})
    ET.SubElement(robot, "link", {"name": "tool0"})

    ET.indent(robot)
    return '<?xml version="1.0"?>\n' + ET.tostring(robot, encoding="unicode")


def _origin_z(joint: ET.Element) -> float:
    origin = joint.find("origin")
    if origin is None:
        return 0.0
    return float(origin.get("xyz", "0 0 0").split()[2])


def load(path: str | Path | None = None) -> Model:
    """Parse a URDF (the committed default model when ``path`` is None) into a :class:`Model`.

    Recovers each revolute joint's axis + ``[min,max]`` limits (radians → degrees) and the link
    length from the *next* joint's origin offset — the inverse of :func:`generate_urdf`, so a
    generated model round-trips exactly.
    """
    urdf_path = Path(path) if path is not None else Path(__file__).parent / _URDF_NAME
    root = ET.parse(urdf_path).getroot()
    all_joints = list(root.iter("joint"))
    revolute = [j for j in all_joints if j.get("type") == "revolute"]

    joints: list[JointGeom] = []
    for i, j in enumerate(revolute):
        axis_el = j.find("axis")
        axis_vals = (axis_el.get("xyz", "0 0 1") if axis_el is not None else "0 0 1").split()
        axis = (float(axis_vals[0]), float(axis_vals[1]), float(axis_vals[2]))
        limit = j.find("limit")
        lower = float(limit.get("lower", "0")) if limit is not None else 0.0
        upper = float(limit.get("upper", "0")) if limit is not None else 0.0
        # length = offset to the next joint (the following <joint>, revolute or the fixed tool).
        idx = all_joints.index(j)
        length = _origin_z(all_joints[idx + 1]) if idx + 1 < len(all_joints) else 0.0
        joints.append(
            JointGeom(
                name=j.get("name", f"joint_{i}"),
                axis=axis,
                length_m=length,
                min_deg=math.degrees(lower),
                max_deg=math.degrees(upper),
            )
        )
    return Model(urdf_path=urdf_path, joints=joints)
