# Flashing `pibot_arm_stm32` onto a Creality 4.2.2 via SD card

The no-wiring route: the 4.2.2 ships with a stock bootloader that flashes a firmware `.bin`
from a FAT32 microSD on power-up. No programmer, no soldering — but there are two hard rules
that bite if you miss them.

## ⚠ Two builds — do not mix them up

The bootloader occupies the first **28 KiB** of flash and loads the application at
**`0x08007000`**. So the SD route needs a build with a **`0x7000` flash offset** — the plain
`0x08000000` build used for SWD **will not boot** if SD-loaded (its vector table is at the
wrong address).

| Build | Offset | File | Route |
| ----- | ------ | ---- | ----- |
| SWD   | `0x08000000` | `../pibotarm.bin` | `../swd/` (OpenOCD via a Pi 5) |
| **SD**| **`0x08007000`** | **`../pibotarm-sd.bin`** | **this one** |

Build the SD binary (the single `build.flash_offset` property shifts both the linker origin and
the runtime `VECT_TAB_OFFSET`):

```bash
arduino-cli compile \
  --fqbn "STMicroelectronics:stm32:GenF1:pnum=GENERIC_F103RETX" \
  --build-property "build.flash_offset=0x7000" \
  --build-property "build.flags.ldspecs=--specs=nano.specs -u _printf_float" \
  --clean --export-binaries firmware/pibot_arm_stm32
cp firmware/pibot_arm_stm32/build/STMicroelectronics.stm32.GenF1/pibot_arm_stm32.ino.bin \
   firmware/pibot_arm_stm32/pibotarm-sd.bin
```

> **Why the `-u _printf_float`:** the STM32 core links newlib-nano by default, which **omits
> float `printf` support** — so `%g`/`%f` emit *nothing* and the joint-angle telemetry comes out
> empty (`<SEQ,joints,*CC`). `-u _printf_float` force-links it (+~5 KB). Without this flag the
> board runs fine but reports no angles. (`atof` on the command path is unaffected.)

Sanity-check the offset took — the reset vector (bytes 4–7, little-endian) must be `>= 0x08007000`:

```bash
od -An -tx4 -N8 firmware/pibot_arm_stm32/pibotarm-sd.bin   # word2 e.g. 0800bf95  ✓
```

## Card prep

- **FAT32**, **MBR** partition scheme. **≤ 8 GB is strongly recommended** — the stock bootloader
  is picky and **large/fast cards are the #1 cause of "it just won't flash."** A 32 GB card
  *may* work but is the first thing to suspect if the board ignores the file.
- One `.bin` at the **root**, in the **mainboard** SD slot.

## Flash procedure

1. Copy the SD build to the card root with a **fresh, unique filename** (8.3-style):
   ```bash
   cp firmware/pibot_arm_stm32/pibotarm-sd.bin /Volumes/<CARD>/pibotarm.bin
   sync && diskutil eject /dev/diskN
   ```
   **Unique name EVERY flash (the #1 gotcha):** the bootloader **ignores a `.bin` whose name
   matches the last one it flashed.** Bump it each time — `pibotarm-a.bin`, `pibotarm-b.bin`, …
2. Power the board **off**, insert the card, power **on**.
3. Wait **~15–20 s** (no progress feedback). The bootloader flashes it and usually renames it
   to `*.CUR` — but `.CUR` rename is unreliable on the 4.2.2, so don't treat its absence as
   failure. Verify by talking to the firmware (below).

## Verify + bench-test (over the board's own USB)

This board has no display once our firmware is on it. The firmware speaks the PiBot protocol
over **USART1 (PA9/PA10) at 115200** — and the 4.2.2's onboard USB-serial chip is wired to
USART1, so the board's **USB cable is the link**. Plug it into the host and bench-test
**comms only first**:

```bash
# the board enumerates as a CH340, e.g. /dev/cu.usbserial-110 on macOS
pibot --help                         # (host CLI; or any 115200 8N1 terminal)
# send `ping` -> expect a pong/telemetry frame. NO motion yet.
```

> ⚠️ The per-joint config in `pibot_arm_stm32.ino` (`JCFG[]`: steps/deg, soft limits, speeds)
> is still **example values**. Tune it to your real arm **before** any `home`/`jvel`/`jmove`,
> or a joint can drive into a hard stop. `ping`/telemetry is always safe; motion is not until
> the config matches the hardware.

## If the board ignores the card

Almost always the **card size/format** (try a ≤8 GB FAT32/MBR card), a **non-unique filename**,
or a **wrong-offset build**. If SD keeps failing, the robust fallback is SWD from a Pi 5 — see
[`../swd/README.md`](../swd/README.md).
