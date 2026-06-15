# Flashing custom firmware onto a Creality 4.2.2 (STM32F103RET6) — research report

**Question:** How do you flash custom firmware onto a Creality 4.2.2 over USB? Is BOOT0 exposed
(which pins to jumper)? Map the real flashing routes.

**Headline verdict (high confidence, multi-source):** **The 4.2.2 has NO accessible BOOT0 jumper,
header, or labeled pad.** BOOT0 is STM32 **chip pin 60** (LQFP64), not broken out to the PCB; to
force it high you'd solder a wire to the MCU pin itself. The onboard CH340's RTS/DTR are **not**
wired to BOOT0/NRST, and there is **no reset button** — so the USB serial-ROM bootloader path
(stm32flash/CubeProgrammer over the CH340) has no auto-entry and no convenient manual entry. It is
*impractical, not impossible*. The two routes people actually use:

1. **SD card** — via the stock Creality bootloader (no wiring; the normal way).
2. **SWD** — via an ST-Link **or a Raspberry Pi + OpenOCD** (recovery, RDP clear, or custom firmware
   built for `0x08000000`).

## 1. BOOT0 / USB-serial — why it's a dead end on this board
- No teardown, pinout, schematic thread, or flashing guide documents a BOOT0 header/pad/test point.
  BOOT0 = chip pin 60 only.
- CH340 ↔ STM32 is **USART1 (PA9 TX / PA10 RX)** — the ROM bootloader's UART *does* exist — **but**
  RTS/DTR are not routed to BOOT0/NRST (no Arduino-style auto-reset), and there's no reset button.
- Every "broken bootloader / install Klipper" guide skips serial+BOOT0 and goes straight to SWD —
  the strongest evidence that BOOT0 is not a usable entry path here.
- `stm32flash` mechanics (for reference only): `stm32flash -w fw.bin -v -g 0x08000000 /dev/ttyUSB0`;
  the STM32 ROM bootloader is **8E1 (even parity)** — stm32flash defaults to that. Irrelevant here
  because you can't get the chip into the bootloader without soldering to pin 60.

## 2. SD-card flashing (the easy route) — rules that bite
- **Stock bootloader pre-installed.** Copy a `.bin` to a microSD root, power-cycle, it self-flashes
  (~15-20 s, no progress feedback). `make flash` / USB-DFU does **not** work on this board.
- **Card:** FAT32, **MBR**, **4096-byte allocation**, **≤8 GB** (smaller is safer; large/fast cards
  are a top failure cause), full format if flaky, single `.bin` at the **root**, **mainboard** slot.
- **Unique filename EVERY flash (the #1 gotcha):** the bootloader **ignores a `.bin` whose name
  matches the last one it flashed**. Bump the name each time (`pibot-a.bin`, `pibot-b.bin`, …).
- **`.CUR` rename is unreliable on the 4.2.2** — don't use it as a success signal; verify by the
  on-screen version / behavior change.
- **⚠ FLASH OFFSET (critical for custom firmware):** the stock bootloader loads the app at the
  **bootloader offset (`0x08007000`, the 28 KiB-bootloader layout)**. Firmware built for
  `0x08000000` (the default `GENERIC_F103RETX`) **will not boot** if SD-loaded — the vector table is
  at the wrong address. To SD-flash custom firmware you must **build it with a `0x7000` flash
  offset** (PlatformIO `board_build.offset = 0x7000`, or the equivalent vector-table offset).

## 3. SWD (the robust route) — works with the Pi you already have
- **No source gives an annotated photo of exact pad coordinates.** The actionable targets: the
  **unpopulated ICP/SWD header footprint** (solder to the pads), and electrically **SWDIO=PA13,
  SWCLK=PA14, NRST, GND, 3V3**. A frequently-repeated "4-pin header above the LCD connector" claim
  came from a search summarizer, **not** a fetched page — verify with a multimeter before soldering.
- **Stock firmware runs `DISABLE_DEBUG`** → normal SWD attach fails; use **connect-under-reset**
  (Marlin issue #25740 documents shorting the **P3 contact** while programming; or wire to NRST).
- **Read-out protection (RDP level 1) is set** → you **must clear RDP first, which mass-erases the
  chip** (and wipes the stock bootloader). Reset/power-cycle after to reload option bytes.
- **Pi-as-programmer (no ST-Link needed):** OpenOCD `bcm2835gpio`/`linuxgpiod`, GPIO25→SWCLK,
  GPIO24→SWDIO, GND→GND, 3V3→3V3; `stm32f1x unlock 0` → `reset halt` →
  `flash write_image erase fw.bin 0x08000000` → `verify_image` → `reset`.
- **Our custom firmware is the `0x08000000` case** (no bootloader) — which is exactly what our
  current `GENERIC_F103RETX` build produces. So **SWD needs no rebuild**; SD does.

## 4. ⚠ Safety checks BEFORE flashing (from the research)
- **Verify the MCU marking:** some "4.2.2" boards ship **STM32F103RC*T6* (256 K)** not **RE*T6*
  (512 K)**, or a **GD32F303/HK32** clone. Wrong-variant images can fail to boot; for a *printer*,
  a 512 K image on a 256 K part is a documented **fire hazard** (our arm firmware drives no heaters,
  but verify the chip anyway so SWD targets the right part).
- Back up stock firmware first (SWD `read`) if you want the option to revert.

## Recommendation for our arm bench-test (task #4)
Two clean options, pick by friction tolerance:
- **SD card, easiest, no wiring** — I rebuild `pibot_arm_stm32` with the **`0x7000` offset**, you drop
  the uniquely-named `.bin` on a FAT32 SD, power-cycle. Keeps the stock bootloader.
- **SWD via the Pi 5 you already have** — current `0x08000000` build works as-is; needs SWD-pad
  wiring + an RDP-clearing mass-erase. More robust, more physical setup.

## Sources
- Klipper Bootloaders — https://www.klipper3d.org/Bootloaders.html
- crysxd gist, Klipper/Katapult on a 4.2.2 (SWD via Pi+OpenOCD) — https://gist.github.com/crysxd/54f758536cf3b45101d195145b55d129
- Dr. Klipper 4.2.7 flash guide (SD = least-bad; ICP header not populated; st-flash --connect-under-reset) — https://www.drklipper.de/doku.php?id=klipper_faq%3Aflash_guide%3Astm32f103%3Acreality_4.2.7
- Marlin issue #25740 (DISABLE_DEBUG kills SWD; short P3; PA13/PA14) — https://github.com/MarlinFirmware/Marlin/issues/25740
- TH3D microSD flashing recommendations (unique filename; FAT32/MBR; card size) — https://tickets.th3dstudio.com/help-guides/article/firmware-flashing-microsd-recommendations
- TH3D 256K-vs-512K CPU warning — https://www.th3dstudio.com/2022/01/16/creality-4-2-x-cpus-512k-swapped-out-for-256k-warning-firmware/
- reprap.org 4.2.2 thread (SD easiest; connect-under-reset; offsets) — https://reprap.org/forum/read.php?415,892514
- Klipper discourse: 4.2.2 schematics (BOOT0 = pin 60) — https://klipper.discourse.group/t/creality-board-4-2-2-and-4-2-7-schematics/3104
- ST community: STM32F1 RDP change forces mass erase — https://community.st.com/t5/stm32-mcus/how-to-change-the-read-out-protection-on-stm32f1/ta-p/49408
- Klipper discourse: some 4.2.2 use GD32F303 — https://klipper.discourse.group/t/support-for-new-creality-boards-4-2-2-with-gd32f303/3016
