# Runbook — Flash an OS image to the Pi

Write a Raspberry Pi OS / Ubuntu image to the Pi's boot media. Two paths: a **removable
device** (SD/USB on this Mac) or the Pi's **onboard NVMe/SD via rpiboot** (USB-C, hold the
power button). Flashing is destructive and guarded by the wrong-disk check plus `--confirm`.

> Recovery if a flash bricks the Pi: restore a prior clone — see
> [eeprom-recovery.md](eeprom-recovery.md) for the bootloader and `pibot provision restore`
> for the disk. Always `pibot provision clone` a known-good system first.

## 1. Preview (writes nothing)

```bash
pibot flash --device /dev/disk4 --image ~/images/ubuntu-24.04.img.xz --dry-run
```

`--dry-run` prints the exact `dd`/imager commands and the wrong-disk guard's decision
without touching the disk.

## 2. Flash a removable device (SD / USB)

```bash
# find the device node first (macOS): diskutil list
pibot flash --device /dev/disk4 \
  --image ~/images/ubuntu-24.04.img.xz \
  --sha256 <expected-sha256> \
  --os ubuntu \
  --hostname pibot \
  --authorized-key-file ~/.ssh/id_ed25519.pub \
  --confirm
```

The guard refuses the system disk, any internal disk, and anything mounted at `/`.

## 3. Flash the onboard NVMe via rpiboot (Pi 5)

```bash
# Put the Pi into USB device mode: power off, hold the power button while
# connecting USB-C to the Mac, keep holding until it enumerates.
pibot flash --target nvme --image ~/images/rpi-os.img.xz --os rpi-os \
  --authorized-key-file ~/.ssh/id_ed25519.pub --confirm
```

See [first-boot.md](first-boot.md) for how the SSH key is embedded for first boot.

## Verify

After the Pi boots from the new image, it should appear on the network and accept the
embedded key without a password:

```bash
pibot discover
pibot run pibot -- uname -a   # passwordless via the embedded key
```
