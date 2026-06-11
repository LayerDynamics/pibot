# Runbook — Emergency stop (e-stop) & the layered fail-safe

How to stop the robot immediately, and the three independent layers that stop it even when
you can't. E-stop is the highest-priority command: it preempts the queue and latches until
explicitly resumed.

## Stop the robot now

```bash
pibot estop pibot          # one-shot: latch e-stop and command a stop
```

During teleop, the **spacebar** latches e-stop and any key release sends `stop`:

```bash
pibot teleop pibot         # WASD/arrows drive, space = e-stop, q = quit
```

## The three fail-safe layers (each independent of the one above)

1. **Operator e-stop** — `pibot estop` / spacebar latches; motion commands are then
   rejected (`rejected: estop`) until resume.
2. **Host deadman watchdog** — if the operator's command stream goes quiet (a dropped
   control connection) the agent commands a `stop` after `watchdog_ms` (default 300 ms).
   Proven end-to-end in [../../tests/e2e/test_agent_e2e.py](../../tests/e2e/test_agent_e2e.py).
3. **Firmware backstop** — the microcontroller runs its own watchdog, so a frozen Pi or a
   dropped wireless link halts the motors with no host involvement (see
   [../../firmware/README.md](../../firmware/README.md)).

## Resume after an e-stop

E-stop is latched on purpose; clear it deliberately once the area is safe. Restarting the
agent (or a fresh `pibot agent start`) clears the host-side latch.

```bash
pibot agent stop pibot && pibot agent start pibot
```

## Verify

Drive, e-stop, then confirm motion commands are refused and the latch is visible:

```bash
pibot estop pibot
pibot cmd pibot drive 0.5 0.0    # expected: refused / e-stop latched
pibot monitor pibot --once       # snapshot shows estop=True
```
