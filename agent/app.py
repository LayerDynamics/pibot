"""The pibotd aiohttp application: routes, auth middleware, and shared agent state.

Endpoints (all behind the bearer-token auth middleware except ``/healthz``):
  GET  /healthz          public liveness
  GET  /health           version + uptime
  GET  /telemetry        snapshot (SPEC-1 §7); WS-upgrade -> periodic push stream
  WS   /control          command frames -> safety -> ack/nak/rejected
  POST /estop            latch e-stop (preempts)
  GET/POST /config       runtime settings store

The :class:`TransportController` (the sole transport owner + safety) is started/stopped
with the app lifecycle; robot telemetry frames are routed into a :class:`RobotTelemetry`.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from aiohttp import web

from agent import __version__
from agent.auth import is_loopback, token_ok
from agent.control import ControlRejected, TransportController
from agent.telemetry import PolicyLink, RobotTelemetry, VcgencmdRun, assemble_snapshot, pi_health
from pibot.logging import get_logger
from pibot.protocol.codec import Message, MessageType
from pibot.transport.base import Transport, TransportError

_log = get_logger("agent.app")

if TYPE_CHECKING:
    from agent.autonomy import AutonomyController
    from agent.video import CameraBroker
    from pibot.arm.kinematics import ForwardKinematics
    from pibot.arm.manager import ArmManager
    from pibot.arm.safety import ArmGate

# Builds the (camera, policy) for an autonomy session from the agent's autonomy config.
AutonomyFactory = Callable[[dict[str, Any]], "tuple[Any, Any]"]


@dataclass
class AgentState:
    """Shared, typed application state."""

    token: str | None = None
    version: str = __version__
    trust_loopback: bool = True
    started: float = field(default_factory=time.monotonic)
    controller: TransportController | None = None
    robot: RobotTelemetry = field(default_factory=RobotTelemetry)
    policy_link: PolicyLink = field(default_factory=PolicyLink)
    vcgencmd_run: VcgencmdRun | None = None
    config: dict[str, Any] = field(default_factory=dict)
    telemetry_interval: float = 0.1
    autonomy: AutonomyController | None = None
    autonomy_config: dict[str, Any] = field(default_factory=dict)
    autonomy_factory: AutonomyFactory | None = None
    broker: CameraBroker | None = None
    video_fps: int = 10
    video_max_dim: int = 640
    # Stepper arm (optional). The drain task is the sole reader of the arm boards' telemetry,
    # mirroring TransportController for the robot link: it refreshes ``arm_positions`` so that
    # concurrent ``GET /arm/telemetry`` requests read a cache instead of racing on ``recv``.
    arm: ArmManager | None = None
    arm_positions: dict[int, float] = field(default_factory=dict)
    arm_positions_ts: float = 0.0
    arm_draining: bool = False
    arm_drain_task: asyncio.Task[None] | None = None
    # Host arm safety gate + the *shared* mutable motion state it reads. The latch and homed-set
    # live here (not per-WS-connection) so every /arm/control client — CLI, app, a reconnect —
    # sees the same latched e-stop and homed joints; the gate validators stay pure.
    arm_gate: ArmGate | None = None
    arm_estopped: bool = False
    arm_homed: set[int] = field(default_factory=set)
    # Forward kinematics (M-ARM-3): a lazily-built ikpy chain (the optional [arm-ik] extra). Built
    # on first /arm/telemetry request when angles exist; absent (pose=None) when the extra isn't
    # installed — the agent core stays numpy-free at module load (NFR-2).
    arm_fk: ForwardKinematics | None = None
    arm_fk_tried: bool = False


STATE: web.AppKey[AgentState] = web.AppKey("pibot_state", AgentState)

PUBLIC_PATHS = frozenset({"/healthz"})

_Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


@web.middleware
async def auth_middleware(request: web.Request, handler: _Handler) -> web.StreamResponse:
    if request.path in PUBLIC_PATHS:
        return await handler(request)
    state = request.app[STATE]
    if state.trust_loopback and is_loopback(request.remote):
        return await handler(request)
    if token_ok(request.headers.get("Authorization"), state.token):
        return await handler(request)
    raise web.HTTPUnauthorized(text="missing or invalid bearer token")


# ---- handlers ------------------------------------------------------------


async def handle_healthz(request: web.Request) -> web.Response:
    return web.Response(text="OK\n")


async def handle_health(request: web.Request) -> web.Response:
    state = request.app[STATE]
    return web.json_response(
        {
            "ok": True,
            "version": state.version,
            "uptime_s": round(time.monotonic() - state.started, 3),
        }
    )


async def _snapshot(state: AgentState) -> dict[str, Any]:
    pi = await asyncio.to_thread(pi_health, state.vcgencmd_run)
    ctrl = state.controller
    transport = ctrl.transport_info if ctrl else {}
    safety = {"estop": ctrl.latched if ctrl else False}
    return assemble_snapshot(
        pi=pi,
        robot=state.robot.snapshot(),
        transport=transport,
        safety=safety,
        ts=time.time(),
        policy=state.policy_link.snapshot(),
    )


async def handle_telemetry(request: web.Request) -> web.StreamResponse:
    state = request.app[STATE]
    ws = web.WebSocketResponse()
    if not ws.can_prepare(request).ok:
        return web.json_response(await _snapshot(state))

    await ws.prepare(request)

    async def _push() -> None:
        try:
            while not ws.closed:
                await ws.send_json(await _snapshot(state))
                await asyncio.sleep(state.telemetry_interval)
        except (ConnectionResetError, asyncio.CancelledError):
            pass

    pusher = asyncio.create_task(_push())
    try:
        # Read incoming frames so the client's close is seen and the handshake completes.
        async for msg in ws:
            if msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSING, web.WSMsgType.ERROR):
                break
    finally:
        pusher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pusher
    return ws


async def handle_ws_control(request: web.Request) -> web.StreamResponse:
    state = request.app[STATE]
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    assert state.controller is not None
    async for msg in ws:
        if msg.type is not web.WSMsgType.TEXT:
            continue
        try:
            data = msg.json()
            command = Message(MessageType.COMMAND, 0, str(data["cmd"]), dict(data.get("args", {})))
        except (ValueError, KeyError):
            await ws.send_json({"error": "bad command frame"})
            continue
        try:
            reply = await state.controller.submit(command)
        except ControlRejected as exc:
            await ws.send_json({"rejected": exc.reason})
            continue
        except TimeoutError:
            await ws.send_json({"error": "no ack"})
            continue
        out: dict[str, Any] = {"ack": reply.type is MessageType.ACK, "seq": reply.seq}
        if reply.type is MessageType.NAK:
            out["nak"] = reply.reason
        await ws.send_json(out)
    return ws


async def handle_estop(request: web.Request) -> web.Response:
    ctrl = request.app[STATE].controller
    if ctrl is not None:
        ctrl.estop()
    return web.json_response({"estop": True})


async def handle_autonomy_start(request: web.Request) -> web.Response:
    """Start in-process closed-loop autonomy, driving through the shared safety gate."""
    state = request.app[STATE]
    if state.controller is None:
        raise web.HTTPServiceUnavailable(text="no transport controller")
    if state.autonomy is not None and state.autonomy.running:
        raise web.HTTPConflict(text="autonomy already running")
    body: dict[str, Any] = {}
    if request.can_read_body:
        with contextlib.suppress(ValueError):  # JSONDecodeError subclasses ValueError
            body = await request.json()

    # Lazy import keeps the ml stack off agent.app's import path.
    from agent.autonomy import AutonomyController, build_policy, build_runtime

    # An explicitly injected factory wins (tests). Otherwise, when the agent opened a shared
    # camera broker at boot, subscribe to it so the /video WS and the autonomy loop consume one
    # capture device; else build_runtime opens its own camera (standalone, no shared broker).
    if state.autonomy_factory is not None:
        camera, policy = state.autonomy_factory(dict(state.autonomy_config))
    elif state.broker is not None:
        from agent.video import BrokerCamera

        camera = BrokerCamera(state.broker.subscribe(), broker=state.broker)
        policy = build_policy(dict(state.autonomy_config))
    else:
        camera, policy = build_runtime(dict(state.autonomy_config))
    auto = AutonomyController(
        state.controller,
        state.policy_link,
        camera=camera,
        policy=policy,
        prompt=str(body.get("prompt", "")),
        control_hz=float(body.get("control_hz", state.autonomy_config.get("control_hz", 20))),
        max_speed=body.get("max_speed"),
    )
    auto.start()
    state.autonomy = auto
    return web.json_response({"autonomy": "started", "prompt": body.get("prompt", "")}, status=201)


async def handle_autonomy_status(request: web.Request) -> web.Response:
    state = request.app[STATE]
    auto = state.autonomy
    return web.json_response(
        {"running": bool(auto and auto.running), "policy": state.policy_link.snapshot()}
    )


async def handle_autonomy_stop(request: web.Request) -> web.Response:
    state = request.app[STATE]
    if state.autonomy is not None:
        await state.autonomy.stop()
        state.autonomy = None
    return web.json_response({"autonomy": "stopped"})


async def handle_config_get(request: web.Request) -> web.Response:
    return web.json_response(request.app[STATE].config)


async def handle_config_post(request: web.Request) -> web.Response:
    state = request.app[STATE]
    data = await request.json()
    state.config.update(data)
    return web.json_response(state.config)


async def _video_push(
    ws: web.WebSocketResponse,
    broker: CameraBroker,
    state: AgentState,
) -> None:
    """Background task: pull frames from the broker and push header+JPEG to ``ws``."""
    from agent.video import encode_jpeg

    q = broker.subscribe()
    seq = 0
    try:
        while not ws.closed:
            try:
                frame = await asyncio.wait_for(q.get(), timeout=1.0)
            except TimeoutError:
                continue
            jpeg, w, h = await asyncio.to_thread(encode_jpeg, frame.data, state.video_max_dim)
            hdr: dict[str, Any] = {
                "seq": seq,
                "ts": frame.ts,
                "w": w,
                "h": h,
                "fmt": "jpeg",
            }
            await ws.send_json(hdr)
            await ws.send_bytes(jpeg)
            seq += 1
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    finally:
        broker.unsubscribe(q)


async def handle_ws_video(request: web.Request) -> web.StreamResponse:
    """WS /video — MJPEG stream behind bearer auth: JSON header + binary JPEG per frame."""
    state = request.app[STATE]
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    broker = state.broker
    if broker is None:
        await ws.close()
        return ws

    pusher = asyncio.create_task(_video_push(ws, broker, state))
    try:
        async for msg in ws:
            if msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSING, web.WSMsgType.ERROR):
                break
    finally:
        pusher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pusher
    return ws


async def _arm_drain(state: AgentState) -> None:
    """Continuously refresh ``state.arm_positions`` from the arm boards' telemetry.

    The **sole** reader of the arm transports' ``recv`` (mirrors :class:`TransportController`
    for the robot link), so concurrent ``GET /arm/telemetry`` requests read a cache instead of
    racing two threads on the same serial port. ``positions(timeout=0.2)`` blocks on the boards,
    so the loop self-paces (~10 Hz on a live board emitting at 100 ms, ~5 Hz idle). Runs until
    ``arm_draining`` is cleared at cleanup, so the worker thread always finishes before
    :meth:`ArmManager.close`.
    """
    assert state.arm is not None
    while state.arm_draining:
        try:
            positions = await asyncio.to_thread(state.arm.positions)
        except Exception:  # noqa: BLE001 — a transport hiccup keeps the last known angles
            await asyncio.sleep(0.1)
            continue
        # positions() reports only what it drained this cycle; an empty result means no frame
        # arrived in this window (not "all joints went to 0"), so keep the last known angles.
        # Merge rather than replace: on a multi-board arm one board may not report every cycle,
        # and overwriting would drop the silent board's joints from the cache.
        if positions:
            state.arm_positions.update(positions)
            state.arm_positions_ts = time.time()


async def _arm_pose(state: AgentState) -> dict[str, float] | None:
    """End-effector pose (FK of the cached joint angles), or ``None`` when no arm/angles or the
    ``[arm-ik]`` extra isn't installed.

    The FK cache (``arm_fk`` / ``arm_fk_tried``) is mutated **only on the event loop** here — the
    heavy work (chain construction, the numpy solve) is offloaded via ``to_thread`` but its result
    is assigned back on the loop, so concurrent telemetry requests can't race on the cache and the
    loop never blocks on numpy (e-stop/control latency unaffected, NFR-1). A missing extra / bad
    model / solve hiccup logs at debug and yields ``None`` rather than breaking the telemetry call.
    """
    if state.arm is None or not state.arm_positions:
        return None
    if state.arm_fk is None and not state.arm_fk_tried:
        state.arm_fk_tried = True  # set before awaiting so a concurrent request won't also build
        try:
            from pibot.arm.kinematics import ForwardKinematics

            state.arm_fk = await asyncio.to_thread(ForwardKinematics)
        except Exception as exc:  # noqa: BLE001 — no [arm-ik] extra / unloadable model
            _log.debug("arm FK unavailable (no [arm-ik] extra or bad model): %s", exc)
            state.arm_fk = None
    fk = state.arm_fk
    if fk is None:
        return None
    positions = dict(state.arm_positions)  # snapshot for the worker thread
    try:
        return await asyncio.to_thread(lambda: fk.solve(positions).as_dict())
    except Exception as exc:  # noqa: BLE001 — never let an FK hiccup break telemetry
        _log.debug("arm FK solve failed: %s", exc)
        return None


async def handle_arm_telemetry(request: web.Request) -> web.Response:
    """Read-only joint angles (deg) per logical joint, served from the drain cache.

    ``age_ms`` is the server-computed age of the cached sample (``None`` until the first one),
    so consumers judge staleness without depending on Pi↔client clock agreement.
    """
    state = request.app[STATE]
    if state.arm is None:
        return web.json_response(
            {
                "ok": True,
                "enabled": False,
                "num_joints": 0,
                "positions": {},
                "homed": {},
                "estopped": False,
                "gripper": None,
                "pose": None,
                "ts": 0.0,
                "age_ms": None,
            }
        )
    ts = state.arm_positions_ts
    age_ms = round((time.time() - ts) * 1000, 1) if ts else None
    grip = state.arm.gripper()
    pose = await _arm_pose(state)
    return web.json_response(
        {
            "ok": True,
            "enabled": True,
            "num_joints": state.arm.num_joints,
            "positions": {str(jid): deg for jid, deg in state.arm_positions.items()},
            # Per-joint homing + the latch state come from the shared gate state the
            # /arm/control handler maintains, so the UI's homed indicator + e-stop lockout
            # reflect real host state (not a guess) across reconnects and multiple clients.
            "homed": {str(jid): jid in state.arm_homed for jid in range(state.arm.num_joints)},
            "estopped": state.arm_estopped,
            # End-effector state (M-ARM-2), drained from the gripper board's `grip` frame.
            "gripper": {"deg": grip.deg, "tool": grip.tool} if grip is not None else None,
            # End-effector Cartesian pose (M-ARM-3 FK); None unless the [arm-ik] extra is installed.
            "pose": pose,
            "ts": state.arm_positions_ts,
            "age_ms": age_ms,
        }
    )


_ARM_ACK: dict[str, Any] = {"type": "ack"}


def _arm_nak(reason: str) -> dict[str, Any]:
    return {"type": "nak", "reason": reason}


def _as_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"expected a number, got {value!r}")
    return int(value)


def _as_float(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"expected a number, got {value!r}")
    return float(value)


def _as_targets(value: Any) -> dict[int, float]:
    if not isinstance(value, dict):
        raise ValueError("targets must be an object of joint -> degrees")
    return {int(k): _as_float(v) for k, v in value.items()}


async def _arm_command(state: AgentState, frame: dict[str, Any]) -> dict[str, Any]:
    """Route one ``/arm/control`` frame through the host gate to the ``ArmManager`` (sends only).

    Every send goes via ``asyncio.to_thread`` so the event loop never blocks on the serial write,
    and **never** calls ``recv`` — ``_arm_drain`` stays the sole reader. The latch + homed set on
    ``AgentState`` are the shared motion state the gate reads.
    """
    arm = state.arm
    gate = state.arm_gate
    if arm is None or gate is None:
        return _arm_nak("no arm configured")
    cmd = frame.get("cmd")
    try:
        # --- whole-arm safety (route straight to ArmManager, no solver code — NFR-1) ---
        if cmd == "estop":
            state.arm_estopped = True  # latch first so it holds even if the send fails
            await asyncio.to_thread(arm.estop)
            return _ARM_ACK
        if cmd == "clear_estop":
            await asyncio.to_thread(arm.clear_estop)
            state.arm_estopped = False  # only drop the latch once the board has been told
            return _ARM_ACK
        if cmd == "enable":
            await asyncio.to_thread(arm.enable, bool(frame.get("on", True)))
            return _ARM_ACK
        # --- end-effector (M-ARM-2) — gate-gated (refused while e-stop latched) ---
        if cmd == "grip":
            res = gate.grip(_as_float(frame["deg"]), estopped=state.arm_estopped)
            if not res.ok:
                return _arm_nak(res.reason)
            await asyncio.to_thread(arm.grip, res.args["deg"])
            return _ARM_ACK
        if cmd == "tool":
            res = gate.tool(estopped=state.arm_estopped)
            if not res.ok:
                return _arm_nak(res.reason)
            await asyncio.to_thread(arm.tool, bool(frame.get("on", True)))
            return _ARM_ACK
        # --- per-joint motion (gate-validated + clamped) ---
        if cmd == "jvel":
            joint = _as_int(frame["joint"])
            res = gate.jvel(joint, _as_float(frame["dps"]), estopped=state.arm_estopped)
            if not res.ok:
                return _arm_nak(res.reason)
            await asyncio.to_thread(arm.jvel, joint, res.args["dps"])
            return _ARM_ACK
        if cmd == "jstop":
            joint = _as_int(frame["joint"])
            res = gate.jstop(joint)
            if not res.ok:
                return _arm_nak(res.reason)
            await asyncio.to_thread(arm.jstop, joint)
            return _ARM_ACK
        if cmd == "jpos":
            joint = _as_int(frame["joint"])
            res = gate.jpos(
                joint, _as_float(frame["deg"]), estopped=state.arm_estopped, homed=state.arm_homed
            )
            if not res.ok:
                return _arm_nak(res.reason)
            await asyncio.to_thread(arm.jpos, joint, res.args["deg"])
            return _ARM_ACK
        if cmd == "jmove":
            joint = _as_int(frame["joint"])
            res = gate.jmove(
                joint,
                _as_float(frame["deg"]),
                _as_float(frame["dps"]),
                estopped=state.arm_estopped,
                homed=state.arm_homed,
            )
            if not res.ok:
                return _arm_nak(res.reason)
            await asyncio.to_thread(arm.jmove, joint, res.args["deg"], res.args["dps"])
            return _ARM_ACK
        if cmd == "home":
            joint = _as_int(frame["joint"])
            res = gate.home(joint, estopped=state.arm_estopped)
            if not res.ok:
                return _arm_nak(res.reason)
            await asyncio.to_thread(arm.home, joint)
            state.arm_homed.add(joint)  # host tracks homing (firmware telemetry carries no flag)
            return _ARM_ACK
        if cmd == "move":
            targets = _as_targets(frame["targets"])
            seconds = _as_float(frame["seconds"])
            current = dict(state.arm_positions)  # snapshot the drain cache for synchronized speeds
            res = gate.move(
                targets, current, seconds, estopped=state.arm_estopped, homed=state.arm_homed
            )
            if not res.ok:
                return _arm_nak(res.reason)
            await asyncio.to_thread(arm.move_synchronized, dict(res.targets), current, seconds)
            return _ARM_ACK
    except (KeyError, ValueError, TypeError) as exc:
        return _arm_nak(f"bad frame: {exc}")
    except (OSError, TransportError) as exc:
        return _arm_nak(f"send failed: {exc}")
    return _arm_nak(f"unknown command: {cmd!r}")


async def handle_arm_control(request: web.Request) -> web.StreamResponse:
    """WS /arm/control — motion frames -> host safety gate -> ArmManager, ack/nak per frame.

    Frames: ``{cmd, joint?, deg?, dps?, seconds?, targets?, on?}`` for
    ``jpos/jmove/jvel/jstop/home/move/enable/estop/clear_estop``. Bearer-token auth like every
    other route (via the app's auth middleware).
    """
    state = request.app[STATE]
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    async for msg in ws:
        if msg.type is not web.WSMsgType.TEXT:
            continue
        try:
            frame = msg.json()
        except ValueError:
            await ws.send_json(_arm_nak("bad frame: not JSON"))
            continue
        if not isinstance(frame, dict):
            await ws.send_json(_arm_nak("bad frame: expected an object"))
            continue
        await ws.send_json(await _arm_command(state, frame))
    return ws


# ---- app construction ----------------------------------------------------


def create_app(
    *,
    token: str | None = None,
    version: str = __version__,
    trust_loopback: bool = True,
    state: AgentState | None = None,
) -> web.Application:
    """Build the base app (health routes + auth). ``build_app`` adds the control surface."""
    app = web.Application(middlewares=[auth_middleware])
    app[STATE] = state or AgentState(token=token, version=version, trust_loopback=trust_loopback)
    app.router.add_get("/healthz", handle_healthz)
    app.router.add_get("/health", handle_health)
    return app


def build_app(
    *,
    transport: Transport,
    token: str | None = None,
    trust_loopback: bool = True,
    vcgencmd_run: VcgencmdRun | None = None,
    deadman_ms: float = 300,
    max_rate_hz: float = 50,
    encoding: str = "ascii",
    telemetry_interval: float = 0.1,
    autonomy_config: dict[str, Any] | None = None,
    autonomy_factory: AutonomyFactory | None = None,
    broker: CameraBroker | None = None,
    video_fps: int = 10,
    video_max_dim: int = 640,
    arm: ArmManager | None = None,
    arm_gate: ArmGate | None = None,
) -> web.Application:
    """Build the full pibotd agent: base app + transport controller + control/telemetry routes."""
    if arm is not None and arm_gate is None:
        from pibot.arm.safety import ArmGate as _ArmGate

        arm_gate = _ArmGate.with_defaults(arm.num_joints)
    state = AgentState(
        token=token,
        trust_loopback=trust_loopback,
        vcgencmd_run=vcgencmd_run,
        telemetry_interval=telemetry_interval,
        autonomy_config=autonomy_config or {},
        autonomy_factory=autonomy_factory,
        broker=broker,
        video_fps=video_fps,
        video_max_dim=video_max_dim,
        arm=arm,
        arm_gate=arm_gate,
    )
    state.controller = TransportController(
        transport,
        on_telemetry=state.robot.ingest,
        deadman_ms=deadman_ms,
        max_rate_hz=max_rate_hz,
        encoding=encoding,
    )
    app = create_app(state=state)

    async def _startup(_app: web.Application) -> None:
        assert state.controller is not None
        await state.controller.start()
        if state.broker is not None:
            await state.broker.start()
        if state.arm is not None:
            # The arm is a peripheral: an absent/unplugged board must NOT take down the agent
            # (robot link, /control, /estop, /video). Mirror build_camera_broker — degrade to
            # "no arm" and keep serving, rather than letting the open escape and abort startup.
            try:
                await asyncio.to_thread(state.arm.open)
            except (OSError, TransportError) as exc:
                _log.warning("arm open failed (%s); /arm/telemetry disabled", exc)
                state.arm = None
            else:
                state.arm_draining = True
                state.arm_drain_task = asyncio.create_task(_arm_drain(state))

    async def _cleanup(_app: web.Application) -> None:
        if state.autonomy is not None:
            await state.autonomy.stop()
        if state.broker is not None:
            await state.broker.stop()
        if state.arm is not None:
            # Clear the flag and let the loop finish its in-flight recv before closing the
            # transports — so the worker thread never reads a port mid-close.
            state.arm_draining = False
            if state.arm_drain_task is not None:
                await state.arm_drain_task
            await asyncio.to_thread(state.arm.close)
        assert state.controller is not None
        await state.controller.stop()

    app.on_startup.append(_startup)
    app.on_cleanup.append(_cleanup)
    app.router.add_get("/telemetry", handle_telemetry)
    app.router.add_get("/control", handle_ws_control)
    app.router.add_post("/estop", handle_estop)
    app.router.add_post("/autonomy", handle_autonomy_start)
    app.router.add_get("/autonomy", handle_autonomy_status)
    app.router.add_delete("/autonomy", handle_autonomy_stop)
    app.router.add_get("/config", handle_config_get)
    app.router.add_post("/config", handle_config_post)
    app.router.add_get("/video", handle_ws_video)
    app.router.add_get("/arm/telemetry", handle_arm_telemetry)
    app.router.add_get("/arm/control", handle_arm_control)
    return app
