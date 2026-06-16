"""/api/arm — stepper-arm telemetry (read-only) + motion proxy (SPEC-4 FR-4).

Every route delegates to ``RobotLink`` (which delegates to ``AgentClient``); pibotd owns the
``ArmManager`` and the host safety gate. **No motion logic lives here** — these are thin proxies
that forward the operator's intent and return pibotd's ack/nak verbatim. A nak (the host gate
refused, e.g. unhomed / latched) is a successful HTTP 200 carrying ``{"type":"nak","reason":…}``;
transport failures surface as 502, and "no robot connected" as 503.
"""

from __future__ import annotations

from typing import Any

from aiohttp import web

from pibot.mc.robot_link import RobotLink
from pibot.mc.state import STATE


def _require_link(request: web.Request) -> RobotLink:
    state = request.app[STATE]
    if state.link is None or not state.link.connected:
        raise web.HTTPServiceUnavailable(text="not connected to robot")
    return state.link


async def _body(request: web.Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except ValueError as exc:  # JSONDecodeError subclasses ValueError
        raise web.HTTPBadRequest(text="body must be JSON") from exc
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="body must be a JSON object")
    return data


async def handle_get_arm_telemetry(request: web.Request) -> web.Response:
    """GET /api/arm/telemetry — proxy pibotd's joint angles ({enabled, num_joints, positions})."""
    link = _require_link(request)
    try:
        result = await link.arm_telemetry()
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm telemetry failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_pose_list(request: web.Request) -> web.Response:
    link = _require_link(request)
    try:
        result = await link.arm_pose_list()
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm pose list failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_pose_post(request: web.Request) -> web.Response:
    link = _require_link(request)
    data = await _body(request)
    try:
        name = None if data.get("name") is None else str(data["name"])
        pose = data.get("pose")
        if name is None and not isinstance(pose, dict):
            raise ValueError("pose create needs name or pose")
        pose_body = pose if isinstance(pose, dict) else None
        target_name = name
        if target_name is None:
            assert pose_body is not None
            target_name = str(pose_body["name"])
        result = await link.arm_pose_save(
            target_name,
            pose_body,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(text=f"pose create failed: {exc}") from exc
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm pose create failed: {exc}") from exc
    return web.json_response(result, status=201)


async def handle_arm_pose_get(request: web.Request) -> web.Response:
    link = _require_link(request)
    try:
        result = await link.arm_pose_get(request.match_info["name"])
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm pose get failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_pose_delete(request: web.Request) -> web.Response:
    link = _require_link(request)
    try:
        result = await link.arm_pose_delete(request.match_info["name"])
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm pose delete failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_program_list(request: web.Request) -> web.Response:
    link = _require_link(request)
    try:
        result = await link.arm_program_list()
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm program list failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_program_post(request: web.Request) -> web.Response:
    link = _require_link(request)
    data = await _body(request)
    try:
        result = await link.arm_program_save(data)
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm program create failed: {exc}") from exc
    return web.json_response(result, status=201)


async def handle_arm_program_get(request: web.Request) -> web.Response:
    link = _require_link(request)
    try:
        result = await link.arm_program_get(request.match_info["name"])
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm program get failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_program_delete(request: web.Request) -> web.Response:
    link = _require_link(request)
    try:
        result = await link.arm_program_delete(request.match_info["name"])
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm program delete failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_program_run(request: web.Request) -> web.Response:
    link = _require_link(request)
    try:
        result = await link.arm_program_run(request.match_info["name"])
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm program run failed: {exc}") from exc
    return web.json_response(result, status=202)


async def handle_arm_program_stop(request: web.Request) -> web.Response:
    link = _require_link(request)
    try:
        result = await link.arm_program_stop()
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm program stop failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_jog(request: web.Request) -> web.Response:
    """POST /api/arm/jog — velocity-jog one joint: ``{joint, dps}``."""
    link = _require_link(request)
    data = await _body(request)
    try:
        joint = int(data["joint"])
        dps = float(data["dps"])
    except (KeyError, TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(text=f"jog needs joint and dps: {exc}") from exc
    try:
        result = await link.arm_jog(joint, dps)
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm jog failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_move(request: web.Request) -> web.Response:
    """POST /api/arm/move — absolute move of one joint: ``{joint, deg, speed?}``."""
    link = _require_link(request)
    data = await _body(request)
    try:
        joint = int(data["joint"])
        deg = float(data["deg"])
        speed = None if data.get("speed") is None else float(data["speed"])
    except (KeyError, TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(text=f"move needs joint and deg: {exc}") from exc
    try:
        result = await link.arm_move_joint(joint, deg, speed)
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm move failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_move_all(request: web.Request) -> web.Response:
    """POST /api/arm/move-all — synchronized multi-joint move: ``{targets:{jid:deg}, seconds}``."""
    link = _require_link(request)
    data = await _body(request)
    try:
        raw = data["targets"]
        targets = {int(k): float(v) for k, v in raw.items()}
        seconds = float(data["seconds"])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise web.HTTPBadRequest(text=f"move-all needs targets and seconds: {exc}") from exc
    try:
        result = await link.arm_move_joints(targets, seconds)
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm move-all failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_move_cartesian(request: web.Request) -> web.Response:
    """POST /api/arm/move-cartesian — Cartesian end-effector move via on-Pi IK:
    ``{x, y, z, seconds, rx?, ry?, rz?}`` (position metres, orientation radians). A nak
    (``IK unavailable`` / ``unreachable`` / unhomed) returns verbatim as HTTP 200."""
    link = _require_link(request)
    data = await _body(request)
    try:
        x = float(data["x"])
        y = float(data["y"])
        z = float(data["z"])
        seconds = float(data["seconds"])
        rx = float(data.get("rx", 0.0))
        ry = float(data.get("ry", 0.0))
        rz = float(data.get("rz", 0.0))
    except (KeyError, TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(text=f"move-cartesian needs x, y, z, seconds: {exc}") from exc
    try:
        result = await link.arm_move_cartesian(x, y, z, seconds, rx=rx, ry=ry, rz=rz)
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm move-cartesian failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_home(request: web.Request) -> web.Response:
    """POST /api/arm/home — home one joint: ``{joint}``."""
    link = _require_link(request)
    data = await _body(request)
    try:
        joint = int(data["joint"])
    except (KeyError, TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(text=f"home needs joint: {exc}") from exc
    try:
        result = await link.arm_home(joint)
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm home failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_estop(request: web.Request) -> web.Response:
    """POST /api/arm/estop — latch the arm e-stop."""
    link = _require_link(request)
    try:
        result = await link.arm_estop()
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm estop failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_clear_estop(request: web.Request) -> web.Response:
    """POST /api/arm/clear_estop — clear the arm e-stop latch."""
    link = _require_link(request)
    try:
        result = await link.arm_clear_estop()
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm clear_estop failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_enable(request: web.Request) -> web.Response:
    """POST /api/arm/enable — energize/release the arm steppers: ``{on}``."""
    link = _require_link(request)
    data = await _body(request)
    on = bool(data.get("on", True))
    try:
        result = await link.arm_enable(on)
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm enable failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_grip(request: web.Request) -> web.Response:
    """POST /api/arm/grip — drive the servo gripper to an absolute angle: ``{deg}``."""
    link = _require_link(request)
    data = await _body(request)
    try:
        deg = float(data["deg"])
    except (KeyError, TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(text=f"grip needs deg: {exc}") from exc
    try:
        result = await link.arm_grip(deg)
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm grip failed: {exc}") from exc
    return web.json_response(result)


async def handle_arm_tool(request: web.Request) -> web.Response:
    """POST /api/arm/tool — energize/release the digital-output tool: ``{on}``."""
    link = _require_link(request)
    data = await _body(request)
    on = bool(data.get("on", True))
    try:
        result = await link.arm_tool(on)
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"arm tool failed: {exc}") from exc
    return web.json_response(result)


def add_arm_routes(app: web.Application) -> None:
    app.router.add_get("/api/arm/telemetry", handle_get_arm_telemetry)
    app.router.add_get("/api/arm/poses", handle_arm_pose_list)
    app.router.add_post("/api/arm/poses", handle_arm_pose_post)
    app.router.add_get("/api/arm/poses/{name}", handle_arm_pose_get)
    app.router.add_delete("/api/arm/poses/{name}", handle_arm_pose_delete)
    app.router.add_get("/api/arm/programs", handle_arm_program_list)
    app.router.add_post("/api/arm/programs", handle_arm_program_post)
    app.router.add_post("/api/arm/programs/stop", handle_arm_program_stop)
    app.router.add_get("/api/arm/programs/{name}", handle_arm_program_get)
    app.router.add_delete("/api/arm/programs/{name}", handle_arm_program_delete)
    app.router.add_post("/api/arm/programs/{name}/run", handle_arm_program_run)
    app.router.add_post("/api/arm/jog", handle_arm_jog)
    app.router.add_post("/api/arm/move", handle_arm_move)
    app.router.add_post("/api/arm/move-all", handle_arm_move_all)
    app.router.add_post("/api/arm/move-cartesian", handle_arm_move_cartesian)
    app.router.add_post("/api/arm/home", handle_arm_home)
    app.router.add_post("/api/arm/estop", handle_arm_estop)
    app.router.add_post("/api/arm/clear_estop", handle_arm_clear_estop)
    app.router.add_post("/api/arm/enable", handle_arm_enable)
    app.router.add_post("/api/arm/grip", handle_arm_grip)
    app.router.add_post("/api/arm/tool", handle_arm_tool)
