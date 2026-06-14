# Flashing `pibot_arm_stm32` onto a Creality 4.2.2 via SWD (from a Raspberry Pi 5)

The Creality 4.2.2 (STM32F103RET6) has **no accessible BOOT0 jumper** and its CH340 isn't
wired for auto-reset, so the USB serial-ROM bootloader is off the table (see
`docs/research/creality-4.2.2-flashing/Report-Final.md`). This board *does* expose a labelled
4-pin **`P2` SWD header**, so we flash it over SWD using a Raspberry Pi 5's GPIO as the
programmer — no ST-Link dongle needed.

Our firmware is built for `0x08000000` (it owns the whole chip — no Creality bootloader kept),
which is exactly what SWD flashing wants. `flash-swd.sh` drives OpenOCD's `linuxgpiod` bit-bang
SWD (the Pi 5's 40-pin GPIO is on the **RP1** I/O chip, so the old `bcm2835gpio` driver does not
work).

## 1. Wiring — 4.2.2 `P2` header → Raspberry Pi 5 (physical pins)

> Confirm the silkscreen labels next to each `P2` pin before wiring — order can vary by board revision.

| 4.2.2 `P2` | Pi 5 pin (physical) | Pi signal |
| ---------- | ------------------- | --------- |
| `SWDIO`    | pin **18**          | GPIO24    |
| `SWCLK`    | pin **22**          | GPIO25    |
| `GND`      | pin **20**          | GND       |
| `VCC`      | **leave disconnected** | — (power the 4.2.2 from its own USB/PSU; don't back-power it) |

Pins 18/20/22 are a neat cluster on the Pi header — three short jumpers. (GPIO24/25 are the
conventional SWD choice; override with `SWDIO_GPIO=` / `SWCLK_GPIO=` if you wire differently.)

## 2. Get the tools + firmware onto the Pi

On the Pi:

```bash
sudo apt-get update && sudo apt-get install -y openocd gpiod   # needs OpenOCD >= 0.12 (Bookworm)
openocd --version                                              # confirm 0.12.x
```

From this Mac, copy the script + the built binary to the Pi (replace the host with yours — e.g.
the Nebula address `192.168.100.2`, or `pi@pibot.local`):

```bash
scp firmware/pibot_arm_stm32/swd/flash-swd.sh \
    firmware/pibot_arm_stm32/pibotarm.bin \
    pi@192.168.100.2:~/
```

`pibotarm.bin` is the current build (rebuild it any time with
`arduino-cli compile --fqbn STMicroelectronics:stm32:GenF1:pnum=GENERIC_F103RETX --export-binaries firmware/pibot_arm_stm32`
then copy `build/STMicroelectronics.stm32.GenF1/pibot_arm_stm32.ino.bin`).

## 3. Flash — two cases

The stock Creality firmware runs Marlin's `DISABLE_DEBUG`, which reclaims the SWD pins a few ms
into boot. So start with `probe`; what it does tells you which path you're on.

```bash
chmod +x ~/flash-swd.sh
~/flash-swd.sh probe
```

### Case A — `probe` prints the IDCODE (debug port reachable)

```bash
~/flash-swd.sh write ~/pibotarm.bin
```

If `write` fails during erase, the chip is read-protected — clear it, power-cycle, retry:

```bash
~/flash-swd.sh unlock          # RDP 1->0 (mass-erases); then power-cycle the board
~/flash-swd.sh write ~/pibotarm.bin
```

### Case B — `probe` times out (DISABLE_DEBUG)

Use the connect-under-power-cycle recovery. It retries the attach in a tight loop; you
**power-cycle the board repeatedly** while it runs, and it grabs the brief boot window before the
firmware disables the port, then mass-erases it (wiping the stock firmware **and** the Creality
bootloader — the board becomes ours-only after this, reflashed via SWD):

```bash
~/flash-swd.sh recover         # power-cycle the board repeatedly while this loops
#   -> on success, POWER-CYCLE once more (option bytes latch on power cycle), then:
~/flash-swd.sh write ~/pibotarm.bin
```

If `recover` exhausts its attempts: try a slower clock (`SPEED_KHZ=50 ~/flash-swd.sh recover`),
recheck the SWDIO/SWCLK/GND wiring, or — only if you can **multimeter-verify a reset point** on
the board — wire it to a Pi GPIO and set `NRST_GPIO=<n>` for reliable connect-under-reset.

## 4. After flashing — bench-test over serial (NOT motion-first)

Once flashed, the firmware talks the PiBot protocol over **USART1 (PA9 TX / PA10 RX)**. Wire that
to a USB-serial adapter (or the board's CH340) and verify **comms only first**:

```bash
# ping -> expect a pong/telemetry frame; read joint telemetry. NO motion yet.
```

> ⚠️ The per-joint config in `pibot_arm_stm32.ino` (`JCFG[]`: steps/deg, soft limits, speeds) is
> still **example values**. Tune it to your real arm **before** any `home`/`jvel`/`jmove`, or a
> joint can drive into a hard stop. Comms (`ping`/telemetry) is always safe; motion is not until
> the config matches the hardware.

## Fallback of last resort — SD card

If SWD turns into a fight, the stock Creality bootloader can flash from a FAT32 microSD — but that
path needs the firmware **rebuilt at the `0x7000` bootloader offset** (our default `0x08000000`
build won't boot when SD-loaded) and a uniquely-named `.bin` each time. Details in
`docs/research/creality-4.2.2-flashing/Report-Final.md` §2.
