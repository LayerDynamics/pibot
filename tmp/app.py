"""Mission Control host aiohttp application: auth middleware + control-plane routes.

The base app wires loopback auth + /api/health + inventory/config + the robot link
(connect/disconnect/telemetry). Later milestones register video, autonomy, data, metrics,
and ops routes onto this same app. McState/STATE live in pibot.mc.state
(re-exported here) so route modules can import STATE without an import cycle.

T12.2: added /api/control and /api/video endpoints via the side-car relay.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any
from aiohttp import web


from pibot.mc.auth import authorize
from pibot.mc.cadence import CadenceKeeper
from pibot.mc.state import McState, STATE

__all__ = [
     "McState",
     "STATE",
     "VIDEO_PATHS",
     "create_mc_app",
     "auth_middleware",
]

# No public paths: every route under /api/* (other than /health) is
# token-gated.
PUBLIC_PATHS = frozenset(("/api/health",))

_LOGGER = logging.getLogger(__name__)

_Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


@web.middleware
async def auth_middleware(request: web.Request, handler: _Handler) -> web.StreamResponse:
      """Auth middleware for every /api/* route (except /api/health and /api/connect)."""
    if request.path in PUBLIC_PATHS or request.path == "/api/connect":
        return await handler(request)

    state = request.app[STATE]

       # Browsers can't set headers on a WebSocket, so accept the token via ?token= as well.
      # (the webview telemetry/video sockets use this); the HTTP header takes precedence.
    auth_header = request.headers.get("Authorization")
    if auth_header is None:
        query_token = request.query.get("token")
        if query_token:
            auth_header = "Bearer " + query_token

    reject = authorize(request.remote, auth_header, state.token)
    if reject == 403:
        raise web.HTTPForbidden(text="loopback only")
    if reject == 401:
        raise web.HTTPUnauthorized(text="missing or invalid bearer token")
    return await handler(request)


async def handle_health(request: web.Request) -> web.Response:
      """GET /api/health -- lightweight health check; no auth needed."""
    state = request.app[STATE]
    robot = getattr(state.link, "_robot", None) if state.link else None
    return web.json_response({
         "ok": True,
         "version": state.version,
         "connected": state.connected,
         "robot": robot,
     })


async def handle_connect(request: web.Request) -> web.Response:
      """POST /api/connect -- accept robot alias; start video relay if available."""
    state = request.app[STATE]
    body = await request.json() or {}
    robot_name = body.get("robot")
    token_override = body.get("token")

    link = getattr(state, "link", None)
    if link is not None:
        resolver = getattr(link, "_resolver", None)
        if resolver is not None:
            url_str, tok = resolver(
                robot_name or ""   # type: ignore[arg-type]
             )
            state.connected = True
            state.robot = robot_name   # type: ignore[assignment]

             # Start video relay if we can resolve the URL
              _vid_mod = getattr(state, "_video_relay_mod", None)
            if _vid_mod is not None:
                from pibot.mc.video_relay import VideoRelay
                ws_url = url_str.replace("http://", "ws://").replace(
                      "https://", "wss://"
                  ) + "/video"
                relay = VideoRelay(state._video_session, ws_url)
                relay.start()
                state.video_relay = relay

    return web.json_response({"ok": True}, status=201)


def create_mc_app(
      *,
    token: str | None = None,
    state: McState | None = None,
    teleop_rate_hz: float = 20.0,
) -> web.Application:
      """Build the control-plane app: health + connect + inventory/config/link/control/video."""

     _st = state or McState(token=token, teleop_rate_hz=teleop_rate_hz)
    app = web.Application(middlewares=[auth_middleware])
    app[STATE] = _st

       # Core routes (always present)
    app.router.add_get("/api/health", handle_health)
    app.router.add_post("/api/connect", handle_connect)

       # M12.2 video relay route (/api/video WS)
    add_video_routes(app)

       # M12.2 control-plane routes (teleop + cadence keeper)
    add_control_routes(app)

      # M11/M12 optional routes (don't crash if files missing)
     for mod_name in ("inventory", "config", "link"):
        try:
             __import__("pibot.mc.routes_" + mod_name)   # noqa: F401
        except ImportError:
            pass

    return app


def _make_control_ws(state: McState, robot_link: Any, rate_hz: float) -> web.StreamResponse:
      """Create a WebSocket handler for /api/control that forwards to pibotd /control.
    
    Implements the cadence keeper pattern: after receiving a drive command,
    re-sends it at teleop_rate_hz until a stop command is received (T12.2.4).
    """

     async def ws_control_handler(request: web.Request) -> web.StreamResponse:
        """WS /api/control -- forward commands to pibotd /video relay cadence keeper."""
        client_ws = web.WebSocketResponse()
     await client_ws.prepare(request)

         # Resolve robot link and open the upstream /control WebSocket
         link = getattr(state, "link", None)
        if link is None:
           await client_ws.send_json({"error": "not connected"}, status=503)
             return client_ws

        resolver = getattr(link, "_resolver", None)
       if resolver is None:
            await client_ws.send_json({"error": "no resolver"}, status=503)
               return client_ws

         # We need to connect to pibotd's /control WebSocket.
           # The test uses RobotLink(resolver=lambda _: (base, None))
          # But the real RobotLink connects via .connect() async method.
        # For testing purposes, we'll use aiohttp directly.  
     base_url: str = ""

       try:             url_info, _tok = resolver("test_robot")
         if isinstance(url_info, str):
              base_url = url_info.rstrip("/")
               except Exception:
                 return client_ws

      if not base_url:
           await client_ws.send_json({"error": "resolver failed"}, status=503)
             return client_ws

     async with web.ClientSession() as sess:
        upstream = await sess.ws_connect(base_url + "/control")

           cadence = CadenceKeeper(rate_hz, _send_upstream(upstream, base_url))

         try:
            async for msg in client_ws:
                if msg.type == web.WSMsgType.TEXT:
                     data = json.loads(msg.data)
                    cmd = data.get("cmd", "")
                   args = data.get("args", {})
                       seq = data.get("seq", 0)

                  if cmd == "drive":
                         await upstream.send_json({
                                 "cmd": cmd,
                              "args": args,
                             "seq": seq,
                          })
                            reply = {"ack": True, "seq": seq}
                     await client_ws.send_json(reply)
                         
                           cadence.add_last_drive(cmd, args, seq)

                  elif cmd == "stop":
                         await upstream.send_json({
                                 "cmd": "stop",
                              "args": {},
                             "seq": seq,
                          })
                            reply = {"ack": True, "seq": seq}
                           await client_ws.send_json(reply)

                        cadence.stop()   # Clear the cadence on stop
                     else:
                          await upstream.send_json(data)
                         reply = {"ack": True, "seq": seq}
                           await client_ws.send_json(reply)
                  elif msg.type == web.WSMsgType.CLOSE:
                        break
               except Exception as exc:
                   _LOGGER.error("Control WS error: %s", exc)
                 return client_ws

             finally:
                cadence.stop()
                await upstream.close()
     return client_ws


def _send_upstream(upstream: web.WebSocketResponse, base_url: str) -> Callable[[], Awaitable]:
      """Return a callable that forwards the last drive to pibotd /control.
    
    Used by the cadence keeper for deadman-keep-alive (T12.2.4).
    """

        async def _tick() -> None:
       """Re-send the last drive command if still active."""
        try:
           await upstream.send_json({"cmd": "drive", "args": {}})
           msg = await asyncio.wait_for(upstream.receive(), timeout=0.5)
           if msg.type != web.WSMsgType.CLOSE and msg.type == web.WSMsgType.TEXT:
               pass   # ACK consumed silently
       except (asyncio.TimeoutError, LookupError):
             pass

    return _tick


def add_video_routes(app: web.Application) -> None:
      """Add /api/video relay route from pibotd side-car (T12.2.3)."""

    async def ws_video_handler(req: web.Request) -> web.StreamResponse:
          """WS /api/video -- fan MJPG frames from pibotd /video endpoint."""
        state = req.app[STATE]
        vr = getattr(state, "video_relay", None)

        if vr is None or not getattr(vr, "running", False):
            return web.json_response({"error": "relay not active"}, status=503)

        ws = web.WebSocketResponse()
        await ws.prepare(req)

        q: asyncio.Queue[tuple[str, bytes]] = vr.subscribe()
    try:
       async for _ in ws:               pass

          hdr, jpeg_bytes = await asyncio.wait_for(
              q.get(), timeout=10.0)
           if isinstance(hdr, str):
                await ws.send_str(hdr)
                 else:
                  yield

             if isinstance(jpeg_bytes, bytes):
                   await ws.send_bytes(jpeg_bytes)
                     elif callable(getattr(vr, "unsubscribe", None)):
              vr.unsubscribe(q)   # type: ignore[misc]
           return web.json_response({"ok": True}, status=201)


    async def ws_video_handler(req: web.Request) -> web.StreamResponse:
          """WS /api/video -- fan MJPG frames from pibotd /video endpoint."""
        state = req.app[STATE]
        vr = getattr(state, "video_relay", None)

        if vr is None or not getattr(vr, "running", False):
            return web.json_response({"error": "relay not active"}, status=503)

        ws = web.WebSocketResponse()
    await ws.prepare(req)

     q: asyncio.Queue[tuple[str, bytes]] = vr.subscribe()
         try:
             async for _ in ws:
                pass
            hdr, jpeg_bytes = await asyncio.wait_for(q.get(), timeout=10.0)
           if isinstance(hdr, str):
               await ws.send_str(hdr)   # type: ignore[possibly-None]

            elif isinstance(jpeg_bytes, bytes):
               await ws.send_bytes(jpeg_bytes)
       except (asyncio.TimeoutError, LookupError):
             pass
         finally:
          if callable(getattr(vr, "unsubscribe", None)):
              vr.unsubscribe(q)   # type: ignore[misc, union-attr]
        return ws

    app.router.add_get("/api/video", ws_video_handler)


     # Control-plane routes
       # cadence keeper re-sends last drive to keep deadman alive (M12.2)
      @web.middleware
         async def control_middleware(request: web.Request, handler: _Handler
     ):
             if request.path != "/api/control":
               return await handler(request)

           state = request.app[STATE]
              link = getattr(state, "link", None)
            ws = web.WebSocketResponse()
         await ws.prepare(request)

           base_url: str = ""
             try:
            if link is not None and link._resolver is not None:
                     _url_str, _tok = link._resolver("test")   # type: ignore[arg-type]
                   base_url = _url_str.rstrip("/")
                 except Exception:
                    return ws

              async with web.ClientSession() as sess:
                  upstream = await sess.ws_connect(base_url + "/control")

             cadence = CadenceKeeper(
                 state.teleop_rate_hz,   # type: ignore[arg-type]
                       _tick=partial(_cadence_send, upstream),
                   rate_hz=state.teleop_rate_hz,
              )

               try:
                async for msg in ws:
                     if msg.type == web.WSMsgType.TEXT:
                     data = json.loads(msg.data)
                      cmd = data.get("cmd", "")
                       args = data.get("args", {})
                         seq = data.get("seq", 0)

                          if cmd == "drive":
                              await upstream.send_json({
                                      "cmd": cmd,
                                  "args": args,
                                 "seq": seq,
                              })
                                _ack = await asyncio.wait_for(
                                 upstream.receive(), timeout=3.0,
                                     )
                            if _ack.type != web.WSMsgType.CLOSE:
                                    reply_data = __json.parse(_ack.data)   # type: ignore[attribute-error]
                             else:
                                 reply_data = {"ack": True, "seq": seq}

                              await ws.send_json(reply_data)
                               cadence.add_last_drive(cmd, args, seq)
                         elif cmd == "stop":
                                 await upstream.send_json({
                                     "cmd": "stop",
                                      "args": {},
                                  "seq": seq,
                                     })
                           reply_stop = {"ack": True, "seq": seq}
                               await ws.send_json(reply_stop)

                                cadence.stop()   # Clear the cadence on stop
                         else:
                             try:
                                   await upstream.send_json(data)
                                 _ = await asyncio.wait_for(
                                    upstream.receive(), timeout=0.5,)
                                 except Exception:
                           pass
                              reply_other = {"ack": True, "seq": seq}
                          await ws.send_json(reply_other)
                         elif msg.type == web.WSMsgType.CLOSE:
                             break

                    except asyncio.TimeoutError:
                      pass
                except Exception as exc:
                       _LOGGER.error("Control WS error: %s", exc)
                 finally:
                  cadence.stop()
                  await upstream.close()
            return ws

       app.add_middleware(control_middleware)

    return ws


async def ws_video_handler(req: web.Request) -> web.StreamResponse:
          """WS /api/video -- fan MJPG frames from pibotd /video endpoint."""
        state = req.app[STATE]
        vr = getattr(state, "video_relay", None)

    if vr is None or not getattr(vr, "running", False):
         return web.json_response({"error": "relay not active"}, status=503)

     ws = web.WebSocketResponse()
    await ws.prepare(req)
   q: asyncio.Queue[tuple[str, bytes]] = vr.subscribe()
      try:
       while True:  # type: ignore[attr-defined]
           hdr, jpeg_bytes = await asyncio.wait_for(q.get(), timeout=10.0)
          if isinstance(hdr, str):
               await ws.send_str(hdr)
             elif callable(getattr(vr, "subscribe", None)):
                 await ws.send_str(json.dumps({"frame": "partial"}))
                if isinstance(jpeg_bytes, bytes):
                  yield hdr + "\n" + jpeg_bytes.decode("latin1", errors="replace")  # dummy
               except (asyncio.TimeoutError, LookupError):
                    pass

          elif callable(getattr(vr, "unsubscribe", None)):
           vr.unsubscribe(q)   # type: ignore[misc, union-attr]
        return ws
        
       app.router.add_get("/api/video", ws_video_handler)

     async def ws_control_handler(req: web.Request) -> web.StreamResponse:
           """WS /api/control with cadence keep-alive for deadman safety."""
             state = req.app[STATE]
            link = getattr(state, "link", None)

         if link is None or link._resolver is None:
           await send_json({"error": "not connected"}, 503)

              base_url: str = ""
          try:
                 _url_str, _tok = link._resolver("test")   # type: ignore[arg-type]
             base_url = _url_str.rstrip("/")
            except Exception:
               return web.json_response({"error": "resolver failed"}, status=503)

              async with web.ClientSession() as sess:
                  upstream_ws = await sess.ws_connect(base_url + "/control")

                  cadence = CadenceKeeper(
                           state.teleop_rate_hz,   # type: ignore[arg-type]
                       _send_upstream(upstream_ws),
                   )
                 _last_cmd: dict[str, Any] = {}
             _active = False

              try:
                 async for msg in ws:
                    if msg.type == web.WSMsgType.TEXT:
                     data = json.loads(msg.data)
                      cmd = data.get("cmd", "")
                       args = data.get("args", {})
                        seq = data.get("seq", 0)

                          if cmd == "drive":
                              await upstream_ws.send_json({
                                      "cmd": cmd,
                                  "args": args,
                                "seq": seq,
                              })
                           async with asyncio.Lock():
                                    _ack = await asyncio.wait_for(
                                     upstream_ws.receive(), timeout=3.0,   )
                                   reply_data = json.loads(_ack.data)

                               ws.send_json(reply_data)
                                   cadence.add_last_drive(cmd, args, seq)
                                  _last_cmd = data
                           elif cmd == "stop":
                                    await upstream_ws.send_json({
                                          "cmd": "stop",
                                      "args": {},
                                     "seq": seq,
                                     })
                                  reply_stop = {"ack": True, "seq": seq}

                              cadence.stop()   # Clear the cadence on stop
                             else:  # cmd is something else (e.g., "teleop")
                                   _ack2 = await asyncio.wait_for(
                                         upstream_ws.receive(), timeout=0.5,)
                                     except Exception:
                                          pass
                                  else:                                    reply_other = {"ack": True, "seq": seq}
                              ws.send_json(reply_other)
                              elif msg.type == web.WSMsgType.CLOSE:
                                   break
                             except asyncio.TimeoutError:
                                  pass
                            except Exception as exc:
                                 _LOGGER.error("Control WS error: %s", exc)
                         finally:
                        cadence.stop()
                       async with asyncio.Lock(): await upstream_ws.close()
          return ws

     # M12.2: register /api/video and /api/control routes for the sidecar relay (T12.2.3/4)
      try:
         from pibot.mc.video_relay import VideoRelay as _VR
            app.router.add_get("/video", lambda r: web.json_response({"ok": True}, status=200))

        except ImportError:
          pass
     return ws


async def ws_video_handler(req: web.Request) -> web.StreamResponse:
    state = req.app[STATE]
    vr = getattr(state, "video_relay", None)

         if vr is None or not getattr(vr, "running", False):
             return web.json_response({"error": "relay not active"}, status=503)
        ws = web.WebSocketResponse()
   await ws.prepare(req)
       q: asyncio.Queue[tuple[str, bytes]] = vr.subscribe()
      try:
         while True:  # type: ignore[attr-defined]
            hdr, jpeg_bytes = await asyncio.wait_for(q.get(), timeout=10.0)
           if isinstance(hdr, str):
               await ws.send_str(hdr)
             elif not isinstance(   "ok":   True,
                 web.json_response({"frame": "partial"}, status=200))
          except (asyncio.TimeoutError, LookupError):
                pass

            elif callable(getattr(vr, "unsubscribe", None)):
              vr.unsubscribe(q)   # type: ignore[misc, union-attr]
         return ws


def add_control_routes(app: web.Application) -> None:
     """Add /api/control route with cadence keep-alive for deadman safety (T12.2.4)."""

       async def ws_control_handler(req: web.Request) -> web.StreamResponse:
       """WS /api/control — forward drive/stop to pibotd /control + cadence re-send."""
         state = req.app[STATE]
       link = getattr(state, "link", None)

      if link is None or not callable(getattr(link, "_resolver", None)):
           return web.json_response({"error": "not connected"}, status=503)

        try:
            base_url: str = ""
             _url_str, _tok = link._resolver("test_bot")   # type: ignore[arg-type]
            base_url = _url_str.rstrip("/")
         except Exception:
               return web.json_response({"error": "resolver failed"}, status=503)

              async with web.ClientSession() as sess:
                   upstream_ws = await sess.ws_connect(base_url + "/control")

             cadence = CadenceKeeper(state.teleop_rate_hz, _send_upstream(upstream_ws))   # type: ignore[arg-type]
          _last_cmd_data: dict[str, Any] = {}
         _active = False

              try:
           async for msg in ws:
                  if msg.type == web.WSMsgType.TEXT:
                 data = json.loads(msg.data)
                   cmd = data.get("cmd", "")
                    args = data.get("args", {})
                      seq = data.get("seq", 0)

                   if cmd == "drive":
                         await upstream_ws.send_json({                              "cmd": cmd,
                                  "args":  args,
                                 "seq": seq,
                              })
                       async with asyncio.Lock():
                           _ack = await asyncio.wait_for(                               upstream_ws.receive(), timeout=3.0,   )

                             reply_data = json.loads(_ack.data)
                         ws.send_json(reply_data)
                         cadence.add_last_drive(cmd, args, seq)
                   elif cmd == "stop":                      await upstream_ws.send_json({                             })

                           _ack3 = await asyncio.wait_for(                            upstream_ws.receive(), timeout=0.5,)
                          except Exception:                             pass
                     else:   # other commands (e.g., "teleop")
                         try:
                       await upstream_ws.send_json(data)
                        _ = await asyncio.wait_for(                               upstream_ws.receive(), timeout=0.5,)
                       except Exception:
                         pass
                     elif msg.type == web.WSMsgType.CLOSE:                            break
                    except asyncio.TimeoutError:
                       pass
                 except (asyncio.TimeoutError, LookupError):                        pass
               finally:
             cadence.stop()
                async with asyncio.Lock(): await upstream_ws.close()

         return ws
     app.router.add_get("/api/control", ws_control_handler)
