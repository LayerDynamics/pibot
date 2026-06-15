# PiBot Control Suite — Usage

Every `pibot` subcommand, grouped by what you're doing. Global flags work on any command:
`--json` (machine-readable output), `--verbose` / `--log-json` (logging), and `--dry-run`
on state-changing commands (preview, change nothing). Targets are inventory aliases (e.g.
`pibot`) or IPs.

See the [runbooks](runbooks/) for end-to-end procedures and
[SPEC-1](specs/SPEC-1-pibot-control-suite.md) for the design.

## Discovery & inventory

```bash
pibot discover                     # scan every local subnet for Raspberry Pis
pibot discover --cidr 192.168.1.0/24 --all
pibot inventory list               # show known robots
pibot inventory add pibot 192.168.1.99 --user ubuntu
pibot inventory alias pibot lab-bot
pibot inventory rm lab-bot
```

## Connection & files (SSH)

```bash
pibot keys install pibot           # install the suite key (one password prompt)
pibot run pibot -- uname -a        # run a remote command
pibot connect pibot                # interactive shell
pibot push pibot ./model.pt /home/ubuntu/model.pt --verify
pibot pull pibot /var/log/syslog ./syslog
pibot tunnel pibot 8787:127.0.0.1:8787   # forward the agent port locally
```

## Provisioning & flashing

```bash
pibot flash --device /dev/disk4 --image ~/img.xz --os ubuntu \
  --authorized-key-file ~/.ssh/id_ed25519.pub --confirm
pibot eeprom pibot status          # bootloader status
pibot eeprom pibot boot-order 0xf416 --confirm   # NVMe-first
pibot provision clone pibot --to backup.img.gz   # back up the NVMe
pibot provision restore pibot --from backup.img.gz --confirm
pibot firmware build firmware/pibot_esp32 --fqbn esp32:esp32:esp32
pibot firmware flash firmware/pibot_esp32 --fqbn esp32:esp32:esp32 --port /dev/ttyUSB0
```

Destructive steps preview with `--dry-run`. See [runbooks/flash.md](runbooks/flash.md) and
[runbooks/eeprom-recovery.md](runbooks/eeprom-recovery.md).

## Driving the robot

```bash
pibot cmd pibot drive 0.5 0.0      # one command, await ACK (clamped + e-stop gated)
pibot cmd pibot ping
pibot estop pibot                  # latch e-stop, command a stop
pibot teleop pibot                 # keyboard drive; space = e-stop
pibot play pibot moves.yaml        # scripted motion sequence
pibot play pibot moves.yaml --dry-run   # print the schedule, send nothing
```

A `moves.yaml` is a list of timed steps:

```yaml
- {at: 0.0, cmd: drive, args: {v: 0.5, w: 0.0}}
- {at: 2.0, cmd: drive, args: {v: 0.0, w: 1.0}}
- {at: 3.0, cmd: stop}
```

See [runbooks/e-stop.md](runbooks/e-stop.md) and
[runbooks/wireless-bringup.md](runbooks/wireless-bringup.md).

## Stepper arm (SPEC-4)

Drive the stepper arm through pibotd's safety-gated `/arm/control` surface. Absolute moves
(`move`, `pose`) require the joint to be homed first; e-stop **latches** until `clear`.

```bash
pibot arm telemetry pibot              # live per-joint angles (read-only)
pibot arm home pibot --all             # home every joint against its endstop
pibot arm jog pibot 0 15               # velocity-jog joint 0 at 15 deg/s (no homing needed)
pibot arm move pibot 1 45              # move joint 1 to 45° at its default speed
pibot arm move pibot 1 45 --speed 20   # …at 20 deg/s
pibot arm move-all pibot 0=90,1=-45 --seconds 2   # synchronized arrival in 2 s
pibot arm pose pibot zero              # the built-in all-joints-zero preset
pibot arm estop pibot                  # latch the arm e-stop
pibot arm clear pibot                  # clear the latch
pibot arm enable pibot                 # energize / pibot arm disable pibot to release
pibot arm jog pibot 0 15 --dry-run     # preview the intent, send nothing
```

Per-joint host limits come from `arm_joint_limits` in `~/.config/pibot/config.toml` (one
`[min_deg, max_deg, max_dps]` triple per joint); see
[runbooks/arm-operation.md](runbooks/arm-operation.md).

## Autonomy (VLA policy — SPEC-2)

The robot streams camera + state observations to a remote policy server (the M4 Max) and
the model drives. Open-loop bring-up logs the policy's actions **without actuating** (the
gate before any closed-loop motion); closed-loop, safety-gated driving lands in M10.

```bash
pibot autonomy pibot --open-loop --prompt "drive to the red ball"   # log actions, no motion
pibot autonomy pibot --open-loop --prompt "follow me"
```

Set the policy server + camera in `~/.config/pibot/config.toml` (`policy_host`,
`policy_port`, `camera_device`, `action_horizon`, `control_hz`). See
[SPEC-2](specs/SPEC-2-pibot-autonomy-platform.md) and the autonomy runbooks.

## The agent, telemetry & deploy

```bash
pibot agent start pibot            # launch pibotd on the Pi
pibot agent status pibot
pibot agent logs pibot --lines 100
pibot agent token                  # generate/show the local bearer token (0600)
pibot monitor pibot                # live telemetry dashboard with threshold alerts
pibot monitor pibot --once --json  # one snapshot, machine-readable
pibot deploy pibot                 # rsync a release, install the systemd unit, health-gate
pibot deploy pibot --dry-run       # preview the change set
pibot deploy pibot --rollback      # restore the previous release
```

## Exit codes

`0` success · `1` runtime error · `2` usage error. `pibot monitor` additionally returns `1`
on a threshold breach and `2` if the agent is unreachable, so it composes in scripts and CI.
