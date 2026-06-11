# Runbook — Bootloader (EEPROM) configuration & recovery

The Pi 5 boot order and bootloader live in an EEPROM, not on the disk. This covers setting
the boot order (e.g. NVMe-first) non-destructively and recovering a Pi that won't boot
after a bad EEPROM change.

> Every write is guarded by `--confirm`. A `boot-order` change rewrites only the
> `BOOT_ORDER=` line and preserves the rest of the config (see
> [../../tests/recovery/test_recovery_paths.py](../../tests/recovery/test_recovery_paths.py)).

## 1. Inspect the current state

```bash
pibot eeprom pibot status     # rpi-eeprom-update: current vs latest
pibot eeprom pibot config     # rpi-eeprom-config: BOOT_ORDER and friends
```

## 2. Preview then set the boot order (NVMe first)

```bash
pibot eeprom pibot boot-order 0xf416 --dry-run   # prints the remote edit, changes nothing
pibot eeprom pibot boot-order 0xf416 --confirm   # 0xf416 = try NVMe, then USB, then SD
```

## 3. Update the bootloader firmware

```bash
pibot eeprom pibot update --confirm   # sudo rpi-eeprom-update -a, then reboot
```

## 4. Recovery — the Pi won't boot after an EEPROM change

The EEPROM cannot be re-flashed over SSH if the Pi won't boot. Use the official recovery
image on a spare SD card:

```bash
# On this Mac, write the bootloader recovery image to a spare SD card with the
# Raspberry Pi Imager (Misc utility images -> Bootloader -> SD/NVMe boot), then:
#   1. power off the Pi, insert the recovery SD card
#   2. power on; the green LED blinks steadily and the EEPROM is reflashed to defaults
#   3. power off, remove the SD card
```

After recovery the EEPROM is back to defaults; re-apply your boot order from step 2.

## Verify

```bash
pibot eeprom pibot status   # reports the bootloader is up to date / the expected version
pibot eeprom pibot config   # BOOT_ORDER shows the value you set
```
