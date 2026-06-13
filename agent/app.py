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
from pibot.protocol.codec import Message, MessageType
from pibot.transport.base import Transport

if TYPE_CHECKING:
    from agent.autonomy import AutonomyController
    from agent.video import CameraBroker

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
) -> web.Application:
    """Build the full pibotd agent: base app + transport controller + control/telemetry routes."""
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

    async def _cleanup(_app: web.Application) -> None:
        if state.autonomy is not None:
            await state.autonomy.stop()
        if state.broker is not None:
            await state.broker.stop()
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
    return app
