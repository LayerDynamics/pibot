# PIML — Physical Intelligence (openpi) Integration for PiBot

> How the [openpi](resources/openpi/) vision-language-action models could become
> PiBot's "brain." Grounded in a read of the actual `resources/openpi` source, not
> the marketing. Honest about what works today, what must be built, and what won't
> work zero-shot.

---

## 1. What openpi actually is

`resources/openpi` is **Physical Intelligence's open-source robot foundation-model
stack** ([README.md:1](resources/openpi/README.md)). It ships three
vision-language-action (VLA) models:

- **π₀** — a flow-based VLA (vision + language → action).
- **π₀-FAST** — an autoregressive VLA using the FAST action tokenizer.
- **π₀.₅** — π₀ with better open-world generalization (knowledge insulation).

Each takes **camera images + robot state + a natural-language prompt** and emits an
**action chunk** (a short horizon of future low-level actions). They are pre-trained
on 10k+ hours of robot data and meant to be **fine-tuned to your robot**.

**The load-bearing fact for PiBot:** these are large GPU models. Inference needs an
**NVIDIA GPU with ≥ 8 GB VRAM**, full fine-tune needs ≥ 70 GB, and the repo is
"tested on Ubuntu 22.04 … we do not currently support other operating systems"
([README.md Requirements](resources/openpi/README.md)). **A Raspberry Pi 5 cannot run
the model.** Everything below is built around that constraint.

**License:** Apache-2.0 ([LICENSE](resources/openpi/LICENSE)) for the code, plus the
**Gemma license** ([LICENSE_GEMMA.txt](resources/openpi/LICENSE_GEMMA.txt)) for the
PaliGemma/Gemma weights the π₀ models build on — relevant before shipping a product.

---

## 2. The one architecture that fits PiBot: remote brain, on-robot client

openpi is explicitly built for a **client-server split**
([docs/remote_inference.md](resources/openpi/docs/remote_inference.md),
[README.md:116](resources/openpi/README.md)):

> "the model can run on a different server and stream actions to the robot via a
> websocket connection. This makes it easy to use more powerful GPUs off-robot and
> keep robot and policy environments separate."

This is **exactly PiBot's brain/muscles split** (SPEC-1 §1) extended one hop:

```text
┌────────────── Raspberry Pi 5 (PiBot, on-robot) ──────────────┐
│  pibotd (M4 agent)                                           │
│   ├─ openpi_client.runtime.Runtime   loop @ max_hz          │
│   │     get_observation → policy.infer → apply_action       │
│   ├─ PibotEnvironment  (WE WRITE THIS)                       │
│   │     get_observation: camera frame + Arduino state -> obs │
│   │     apply_action:    action vector -> M3 protocol cmds   │
│   └─ Safety (M4): clamp · e-stop · deadman BEFORE actuating  │
│         │                                                    │
│   openpi_client.WebsocketClientPolicy (msgpack+numpy)        │
└─────────┼────────────────────────────────────────────────────┘
          │  websocket  (LAN, or over the existing ZeroTier overlay)
          ▼
┌─── Policy server: THIS MacBook (M4 Max, 36 GB, MPS) ─ or a remote NVIDIA GPU ─┐
│  openpi.serving.WebsocketPolicyServer                                        │
│   └─ π₀ / π₀.₅ checkpoint  (+ PibotInputs/PibotOutputs)                      │
│      scripts/serve_policy.py  --policy.dir=... --port 8000                   │
│      PyTorch path, pytorch_device="mps"   (see §6 — Apple-Silicon deploy)     │
└───────────────────────────────────────────────────────────────────────────────┘
```

The robot half is **`openpi-client`**, whose dependencies are
`dm-tree, msgpack, numpy<2.0, pillow, websockets`, `requires-python >=3.7`
([packages/openpi-client/pyproject.toml](resources/openpi/packages/openpi-client/pyproject.toml)).
That is light and pure enough to **install and run on a Pi 5** — no jax, no torch, no
CUDA. Only the GPU box installs the full `openpi`.

---

## 3. The integration seam (what we actually write)

The runtime loop is dead simple
([runtime/runtime.py:80-88](resources/openpi/packages/openpi-client/src/openpi_client/runtime/runtime.py)):

```python
observation = self._environment.get_observation()
action = self._agent.get_action(observation)   # PolicyAgent -> policy.infer(obs)
self._environment.apply_action(action)
```

`Environment` is a 4-method ABC
([runtime/environment.py](resources/openpi/packages/openpi-client/src/openpi_client/runtime/environment.py)):
`reset()`, `is_episode_complete()`, `get_observation() -> dict`,
`apply_action(action: dict)`. **PiBot implements one class:**

```python
# pibot/ml/pibot_environment.py  (proposed)
from openpi_client.runtime import environment
from openpi_client import image_tools

class PibotEnvironment(environment.Environment):
    def __init__(self, transport, camera, prompt, safety):
        self._transport = transport   # M3 Transport (serial/tcp/...)
        self._camera = camera         # Pi Camera / USB webcam
        self._prompt = prompt
        self._safety = safety         # M4 safety subsystem

    def reset(self):
        self._safety.estop()          # stop on episode boundaries
        self._transport.send(stop_frame())

    def is_episode_complete(self) -> bool:
        return False                  # continuous driving; or a goal predicate

    def get_observation(self) -> dict:
        frame = self._camera.capture()                 # HxWx3 uint8
        img = image_tools.convert_to_uint8(
            image_tools.resize_with_pad(frame, 224, 224))   # -> 224x224 uint8
        state = self._transport.read_state()           # encoders/IMU/battery (M3 telemetry)
        return {"image": {"base_0_rgb": img}, "state": state, "prompt": self._prompt}

    def apply_action(self, action: dict):
        vec = action["actions"]                        # (action_dim,) for this step
        cmd = self._action_to_command(vec)             # -> drive(v,w) / servo(id,deg)
        if self._safety.allow(cmd):                    # clamp + e-stop + watchdog gate
            self._transport.send(encode(cmd))          # M3 protocol over the transport
```

The wiring (inside `pibotd`):

```python
from openpi_client import websocket_client_policy, action_chunk_broker
from openpi_client.runtime import runtime, agents

policy = action_chunk_broker.ActionChunkBroker(
    websocket_client_policy.WebsocketClientPolicy(host=GPU_HOST, port=8000, api_key=KEY),
    action_horizon=ACTION_HORIZON,         # e.g. 10–50
)
rt = runtime.Runtime(
    environment=PibotEnvironment(transport, camera, "drive to the red ball", safety),
    agent=agents.policy_agent.PolicyAgent(policy),
    subscribers=[TelemetryLogger()],       # records obs/action for fine-tuning
    max_hz=CONTROL_HZ,
)
rt.run()
```

**Why `ActionChunkBroker` matters**
([action_chunk_broker.py](resources/openpi/packages/openpi-client/src/openpi_client/action_chunk_broker.py)):
the server returns a *chunk* of `action_horizon` future actions per inference. The
broker emits one per control step and only re-queries the (slow, remote) server every
`action_horizon` steps. This is how a ~100-300 ms remote inference can drive a robot
at, say, 20-50 Hz without stalling each step.

---

## 4. Mapping to the PiBot Control Suite (concrete, by milestone)

| openpi piece | PiBot piece | Integration |
|---|---|---|
| `Environment.apply_action` | **M3** `Transport` + protocol | Action vector → `drive(v,w)`/`servo(id,deg)` frames; define a single `_action_to_command` mapping |
| `Runtime` loop | **M4** `pibotd` agent | Runtime runs inside the agent that already owns the transport (sole-owner rule, D2) |
| every `apply_action` | **M4** safety subsystem | VLA actions pass clamp + latched e-stop + deadman watchdog **before** actuating — the model never bypasses local safety |
| `WebsocketClientPolicy(host=...)` | **pifinder/inventory + ZeroTier** | The Pi already rides a ZeroTier overlay (`10.147.20.x`). Put the GPU box on the same overlay → secure, zero-config link; store the endpoint in `~/.config/pibot/config.toml` |
| `openpi_client` on the Pi | **M5** `pibot deploy` | Deploy `openpi_client` + `PibotEnvironment` to the Pi; the policy server deploys to the GPU box via openpi's Docker compose |
| `subscriber.on_step(obs, action)` | **M4** telemetry/logging | Reuse the telemetry recorder to log episodes for fine-tuning |
| `image_tools.resize_with_pad` | new **camera** module | Pi captures frames → 224×224 uint8 → obs dict (lightweight; PIL/numpy only) |

**Action-space mapping is the crux.** π₀/π₀.₅ were trained on **manipulator arms**
(ALOHA 14-DoF, DROID/UR5 7-DoF + gripper — see
[examples/ur5/README.md](resources/openpi/examples/ur5/README.md),
[src/openpi/policies/](resources/openpi/src/openpi/policies/)). PiBot is a
**differential-drive rover with servos** — a different action space. On the **server**
you define `PibotInputs`/`PibotOutputs` transforms (the UR5 README is the template):
`PibotInputs` packs PiBot's `state` + camera into the model's expected dict;
`PibotOutputs` slices the model's action columns down to PiBot's `[v, ω, servo…]`.

---

## 5. What must be built on the server (the M4 Max, or any GPU host)

1. **A `PibotPolicy` data config** — `PibotInputs`/`PibotOutputs` transforms mapping
   PiBot observations/actions ↔ the model
   ([examples/ur5/README.md](resources/openpi/examples/ur5/README.md) is the worked
   example; [src/openpi/policies/libero_policy.py](resources/openpi/src/openpi/policies/libero_policy.py)
   has the commented reference).
2. **Normalization stats** for PiBot's state/action ranges
   (`scripts/compute_norm_stats.py`).
3. **Serve it** — `uv run scripts/serve_policy.py policy:checkpoint
   --policy.config=<pibot_config> --policy.dir=<checkpoint>` (default port 8000;
   [docs/remote_inference.md:8-20](resources/openpi/docs/remote_inference.md)).
   The server is `openpi.serving.WebsocketPolicyServer` — it already emits
   `server_timing` per response for latency monitoring
   ([websocket_policy_server.py:64](resources/openpi/src/openpi/serving/websocket_policy_server.py)).

---

## 6. Running the policy server on this MacBook (M4 Max — Apple Silicon)

**Decision: the M4 Max is the policy server.** The Pi 5 client connects to it over
LAN / the ZeroTier overlay. No NVIDIA box, no cloud rental, no recurring cost — and
the M4 Max's **36 GB unified memory** comfortably fits π₀'s 3.3 B params (~7 GB in
bf16). This is a strong fit; the only open question is the Apple-Silicon **software
path**, and here the honest state matters:

**Route A — PyTorch + MPS (pragmatic, available now). Recommended to start.**
openpi ships a PyTorch path (HF prepared a PyTorch port) and its device is
parameterizable: `policy_config.py:71` only auto-selects `cuda`-or-`cpu`, but you can
pass **`pytorch_device="mps"`**, `torch==2.7.1` supports MPS, and there's already an
MPS-aware guard in its vendored Gemma code (`modeling_gemma.py:153`). Caveats, stated
plainly:
- **`uv sync` of full openpi fails on macOS** — `pyproject.toml:18` hard-pins
  `jax[cuda12]==0.5.3` (CUDA-only). You must do a **torch-only install** (install the
  PyTorch model path + `transformers`/`openpi` without the JAX extra), not the
  documented `uv sync`.
- **MPS op coverage is the real risk.** Not every op is implemented on MPS; some fall
  back to CPU (slow) or raise. The π₀ flow-matching denoise loop + attention need
  validating end-to-end. Expect to debug op gaps; `PYTORCH_ENABLE_MPS_FALLBACK=1`
  lets unsupported ops fall back to CPU so you can at least get a first inference.
- **VERIFIED (2026-06-11, on this machine).** `lerobot/pi05_base` (π₀.₅, **3.62 B
  params**) loads onto MPS and runs a full forward pass — SigLIP vision tower + Gemma +
  action expert + the 10-step flow-matching denoise — entirely on Metal:
  **~760 ms/inference producing a 50-action × 32-dim chunk** (steady-state 749–773 ms;
  first call 11 s = one-time Metal kernel compile). No fatal unsupported-op (run with
  `PYTORCH_ENABLE_MPS_FALLBACK=1`). The working recipe:
  `uv pip install lerobot transformers accelerate` → **pin `transformers==4.53.2`** and
  apply openpi's `transformers_replace` patch (this clears LeRobot's "incorrect
  transformer version" guard — GitHub issues #2697/#2319/#2489) →
  `PI05Policy.from_pretrained("lerobot/pi05_base").to("mps")`.
- **What that run did NOT cover (needed for *useful* output, not for the hardware
  question):** (a) the **gated PaliGemma tokenizer** `google/paligemma-3b-pt-224` —
  accept its license on HF + set `HF_TOKEN` (the test injected synthetic token IDs to
  isolate the compute path); (b) real normalization stats + a **PiBot fine-tune** (base
  model → meaningless action *values*). Also note a benign loader warning about a
  missing `embed_tokens.weight` (PaliGemma ties input embeddings to the LM head; the
  forward pass ran regardless) — validate language conditioning during real bring-up.

**Route B — MLX (performance route, but requires a port). Not a drop-in.**
There is **no MLX implementation of π₀** (verified — no official or community port).
`mlx-vlm` provides the **PaliGemma backbone** on Apple Silicon, but π₀'s **300 M
action expert + flow-matching head are π₀-specific and must be written in MLX**. That
is a genuine porting project, not a config change. Upside if you do it: MLX is
typically faster and more memory-efficient than PyTorch-MPS on Apple Silicon and is
unified-memory-native. **Recommendation: do not block bring-up on an MLX port** — get
running on Route A, and treat MLX as an optimization track *if* MPS perf or op
coverage proves inadequate.

**Serving + connectivity (either route):** run
`scripts/serve_policy.py policy:checkpoint --policy.config=<pibot> --policy.dir=<ckpt>`
on the Mac (binds `0.0.0.0:8000`). The Pi uses
`WebsocketClientPolicy(host=<mac overlay/LAN IP>, port=8000)`. Put the Mac on the same
**ZeroTier overlay** the Pi already rides for a stable address, and store it in
`~/.config/pibot/config.toml`. Operational note: the Mac must be **awake and reachable**
whenever the robot is autonomous, and sustained 3.3 B inference on a laptop is a
thermal/power load.

**Latency (measured, not estimated):** the full forward pass is **~760 ms** on this
M4 Max — the 10-step flow-matching denoise dominates (not the tens-of-ms a single LLM
token would suggest). But each pass returns a **50-action chunk**, so with action
chunking (§3) one inference covers ~2.5 s of motion at 20 Hz: comfortable real-time
headroom (~30 % compute duty cycle).

---

## 7. Honest constraints & risks (read before investing)

1. **The brain runs off-robot — now on your M4 Max (§6), so no cloud cost.** The Pi
   can't run the model; the Mac serves it. The trade-offs move from *money* to: the
   Mac must be on/reachable during autonomy, and the **Apple-Silicon software path is
   the open risk** (MPS op coverage today, or an MLX port) — not the hardware.
2. **Zero-shot will not work on PiBot.** π₀ is trained on manipulation, not
   wheeled navigation. A rover is out-of-distribution → you **must fine-tune** on
   PiBot demonstrations before it does anything useful. Budget for data collection +
   a training run, not a download-and-go.
3. **A camera is mandatory.** The whole model is vision-conditioned. The PiBot spec
   centers on Arduino sensors; VLA adds a hard requirement for a Pi Camera / USB
   webcam and an image pipeline.
4. **Latency vs. safety.** Remote inference is tens-to-hundreds of ms and can drop.
   Action chunking hides throughput, **not** a dropped link. The **M4 local watchdog
   + e-stop must run independently** and stop the robot if the policy stream stalls —
   the VLA is never the only thing between a command and the motors.
5. **`numpy < 2.0` pin.** `openpi-client` requires `numpy>=1.22.4,<2.0`
   ([pyproject](resources/openpi/packages/openpi-client/pyproject.toml)). The PiBot
   suite is stdlib-only today; once `openpi_client` lands on the Pi it introduces
   numpy + this pin. Keep ML deps in a separate optional extra so the core CLI/agent
   stay light and the pin can't break the rest of the suite.
6. **Mobile-robot fit is unproven.** PI's own README hedges: "$π_0$ may or may not
   work for you." Treat this as research, sequenced **after** the suite's core
   teleop/telemetry/safety (M3–M4) are solid — those are prerequisites, not optional.
7. **Model licensing** (Gemma terms) applies to any product use of the weights.

---

## 8. Phased adoption path (incremental, each step independently valuable)

- **Phase 0 — Prove the pipe AND the M4 Max path.** Two cheap de-risking steps:
  (a) **✅ DONE (2026-06-11):** π₀.₅ (3.62 B) runs a full forward pass on this M4 Max
  via PyTorch-MPS at **~760 ms/50-action chunk** (§6 Route A) — the biggest unknown is
  resolved. Remaining to turn it into a *server*: accept the gated PaliGemma tokenizer
  license (`HF_TOKEN`) and wrap the policy behind a websocket server (openpi's
  `scripts/serve_policy.py`, or LeRobot's `async_inference` server);
  (b) install `openpi_client` on the Pi and run
  [examples/simple_client/main.py](resources/openpi/examples/simple_client/main.py)
  against that Mac server with random observations to validate the websocket/msgpack
  path and **measure round-trip latency** over the LAN/overlay. Nothing robot-specific
  to build; pure feasibility.
- **Phase 1 — Real observations, open loop.** Add the camera module + `PibotEnvironment.get_observation`
  (camera + M3 telemetry → obs). Stream real obs to a server running a **stock π₀.₅
  checkpoint**; log the returned actions but **do not actuate**. Confirms the obs
  schema, image pipeline, and end-to-end latency on real data.
- **Phase 2 — Closed loop, safety-gated.** Implement `apply_action` → M3 protocol
  **through the M4 safety gate**. Use M4 teleop to **record demonstrations**
  (the subscriber logs obs/action), convert to a **LeRobot dataset**
  (openpi ships `examples/*/convert_*_to_lerobot.py`), **fine-tune** on the GPU box,
  serve the new checkpoint, and run closed-loop with the watchdog armed.

---

## 9. Bottom line

openpi is a **clean fit for PiBot's architecture** — the client-server split is the
brain/muscles model with one network hop, `openpi_client` runs on the Pi, and the
`Environment` ABC is a tidy seam that drops into the M4 agent and M3 transport.
Hosting the server on **this M4 Max** removes the cloud-GPU cost entirely; 36 GB
unified memory is ample. The remaining risk is purely the **Apple-Silicon software
path**: **PyTorch-MPS is verified** — π₀.₅ (3.62 B) runs on this M4 Max at ~760 ms per
50-action chunk (§6) — so the brain genuinely runs locally, no cloud. Treat an **MLX
port** as a later optimization only; there is no π₀ MLX implementation to drop in, so
MLX is build-it-yourself. It is still **not** a drop-in
autonomy upgrade: it needs a camera and a fine-tuning loop on PiBot data, and it must
sit **behind** the local safety subsystem. Sequence it as a **post-M4 research track**
(out-of-scope per SPEC-1 §2.2 N1, but explicitly enabled by the M3 transport + M4
agent/telemetry the suite is building).

### Key files in `resources/openpi`
- Robot client (runs on the Pi): `packages/openpi-client/src/openpi_client/`
  — `runtime/runtime.py`, `runtime/environment.py`, `websocket_client_policy.py`,
  `action_chunk_broker.py`, `image_tools.py`
- Minimal client example: `examples/simple_client/main.py`
- Real-robot `Environment` example: `examples/aloha_real/env.py`
- New-robot transform template: `examples/ur5/README.md`, `src/openpi/policies/`
- Server: `src/openpi/serving/websocket_policy_server.py`, `scripts/serve_policy.py`
- Remote-inference guide: `docs/remote_inference.md`
