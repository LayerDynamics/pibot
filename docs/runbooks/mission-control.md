# Runbook — PiBot Mission Control (M12)

The Mission Control desktop app (Tauri + React + Python sidecar) is the single pane of
glass for operating PiBot: connect, teleop, autonomy, data collection, fine-tuning, and
provisioning. This runbook covers first launch through steady-state operations.

## Prerequisites

- macOS 14+ (Sonoma / Sequoia) on the M4 Max
- PiBot Mission Control `.app` installed (or run from source: `cd app && pnpm tauri dev`)
- `pibotd` running on the Pi and reachable over Nebula (or USB serial)
- A `NEBULA_KEY` set in the environment (or injected by the sidecar at launch)

## 1. Launch and Connect

```bash
# From source (dev)
cd app && pnpm tauri dev

# From installed app bundle
open /Applications/PiBot\ Mission\ Control.app
```

1. Enter the robot ID (e.g. `pibot`) and the per-launch token displayed by `pibotd`.
2. Click **Connect**.
3. The Dashboard tab should show live `temp_c`, `battery_v`, and a green **Transport** badge.

## 2. Teleop

1. Navigate to the **Teleop** tab.
2. Use WASD keys or a connected gamepad to drive.
3. The status bar shows ACK latency — values above 200 ms indicate a degraded link.
4. Press **Escape** or the red **E-STOP** button to latch the e-stop immediately.

## 3. Autonomy

1. Navigate to the **Autonomy** tab.
2. Enter a task prompt (e.g. `"drive to the red ball"`).
3. Enter the policy server URL (default `ws://127.0.0.1:8000`).
4. Click **Start**. The policy-link latency chart begins updating each inference cycle.
5. Click **Stop** to return to idle. The drop-to-stop failsafe fires automatically if the
   link is lost for > 2 s.

## 4. Data Collection

1. Navigate to the **Data** tab → **Episodes** sub-tab.
2. Click **Start Recording**, enter a task label, then drive a demonstration.
3. Click **Stop Recording** to finalise the episode.
4. Episodes appear in the episode list; click any row to see the replay bundle.

## 5. Fine-Tuning

1. Navigate to **Data** → **Fine-Tune** sub-tab.
2. Select an episode dataset and click **Create Run**.
3. Training starts in the background; status updates from `queued → running → done`.
4. Click **Serve Checkpoint** on a completed run to load it into the policy server.

## 6. Metrics

1. Navigate to **Data** → **Metrics** sub-tab.
2. Set a time window and click **Load** to plot `temp_c` and `battery_v` history.
3. Click **Export JSON** or **Export CSV** to download the time-series.
4. Click **Prune** to remove rows older than 30 days (retention policy).

## 7. Provisioning

> **STOP.** The **flash**, **clone**, **restore**, and **eeprom** operations are
> **destructive** and cannot be undone. Read the entire flow before clicking Confirm.

1. Navigate to the **Provisioning** tab.
2. Select an operation from the dropdown (e.g. `flash`).
3. Click **Preview** — this runs a dry-run and shows what *would* happen.
4. Review the preview output in the log panel.
5. Check the **"I understand this is destructive"** checkbox in the confirmation modal.
6. Click **Confirm**. The operation runs; the log panel streams output in real time.
7. If anything looks wrong, click **Cancel** before the operation completes.

## 8. E-Stop Recovery

1. Identify and resolve the cause of the e-stop (hardware fault, overtemp, etc.).
2. Disconnect Mission Control (click **Disconnect**).
3. Power-cycle the Pi if necessary.
4. Reconnect — a new session clears the latch.

## Verify

```bash
# Smoke-test the sidecar HTTP API directly (no UI required)
# Requires: PIBOT_TOKEN set to the per-launch token
curl -s -H "Authorization: Bearer $PIBOT_TOKEN" http://127.0.0.1:8765/api/health | python3 -m json.tool
```

Expected output contains `"status": "ok"` and a non-null `"robot"` field when connected.

```bash
# Confirm metrics writes are flowing
curl -s -H "Authorization: Bearer $PIBOT_TOKEN" \
  "http://127.0.0.1:8765/api/telemetry/history?from=0&to=9999999999" | python3 -m json.tool
```

Expected: a JSON array; non-empty after ≥ 5 s of active connection.
