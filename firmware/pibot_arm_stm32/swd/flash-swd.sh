#!/usr/bin/env bash
# Flash pibot_arm_stm32 onto a Creality 4.2.2 (STM32F103RET6) via SWD, using a Raspberry Pi 5's
# GPIO as the programmer (OpenOCD bit-bang, linuxgpiod driver — the Pi 5 uses the RP1 I/O chip, so
# the old bcm2835gpio driver does NOT work). Run this ON the Pi that is wired to the board.
#
# Wiring — 4.2.2 "P2" SWD header  ->  Pi 5 40-pin header (physical pins):
#     SWDIO -> GPIO24  (pin 18)
#     SWCLK -> GPIO25  (pin 22)
#     GND   -> GND     (pin 20)
#     VCC   -> leave DISCONNECTED; power the 4.2.2 from its own USB/PSU (do not back-power it).
#
# The catch: the stock Creality firmware runs Marlin's DISABLE_DEBUG, which reconfigures the SWD
# pins (PA13/PA14) as GPIO a few ms into boot — so a plain attach against a board running its
# stock firmware will TIME OUT. There are two cases, and this script handles both:
#
#   A. EASY CASE — `probe` reads the IDCODE (debug port is reachable). Just:
#        ./flash-swd.sh probe                 # confirms wiring + a live debug port
#        ./flash-swd.sh write fw.bin          # flash + verify at 0x08000000, then run
#      If `write` fails during erase, the chip is read-protected (RDP) — run `unlock`, power-cycle,
#      then `write` again.
#
#   B. DISABLE_DEBUG CASE — `probe` TIMES OUT. Use the connect-under-power-cycle recovery, which
#      retries the attach in a tight loop and grabs the brief window after reset-deassert but
#      before the stock firmware disables the port, then MASS-ERASES it (wiping the stock firmware
#      + Creality bootloader — this board will thereafter be ours-only, flashed via SWD):
#        ./flash-swd.sh recover               # then POWER-CYCLE the board repeatedly while it loops
#        #   -> POWER-CYCLE once more after it reports success (option bytes latch on power cycle)
#        ./flash-swd.sh write fw.bin
#
# Overrides (env): SWDIO_GPIO=24 SWCLK_GPIO=25 SPEED_KHZ=100 GPIOCHIP=0 RETRIES=300
#   NRST_GPIO=<n>  — OPTIONAL. Only set this if you have *verified with a multimeter* a reset point
#                    on the board and wired it to that Pi GPIO. It enables connect-under-reset
#                    (reliable), but DO NOT guess a pad — an unverified reset wire can damage things.
set -euo pipefail

SWDIO_GPIO="${SWDIO_GPIO:-24}"
SWCLK_GPIO="${SWCLK_GPIO:-25}"
NRST_GPIO="${NRST_GPIO:-}"        # optional; only if you verified a reset point — see header
SPEED_KHZ="${SPEED_KHZ:-100}"     # slow first-attach: bit-bang SWD over jumpers on RP1 is flaky
RETRIES="${RETRIES:-300}"         # `recover` attach attempts (power-cycle the board during them)
FLASH_ADDR="0x08000000"           # our firmware owns the whole chip (no Creality bootloader kept)

die() { echo "ERROR: $*" >&2; exit 1; }

command -v openocd >/dev/null 2>&1 || die "openocd not installed — run: sudo apt-get install -y openocd"
ver="$(openocd --version 2>&1 | head -1)"
echo "$ver"
# The `adapter gpio <sig> -chip N <gpio>` syntax used below needs OpenOCD >= 0.12 (Raspberry Pi OS
# Bookworm ships 0.12; Bullseye ships 0.11 and will fail to parse it).
vernum="$(printf '%s\n' "$ver" | grep -oE '[0-9]+\.[0-9]+' | head -1)"
maj="${vernum%%.*}"; min="${vernum#*.}"
if [ "${maj:-0}" -eq 0 ] && [ "${min:-0}" -lt 12 ]; then
  echo "WARNING: OpenOCD $vernum is < 0.12 — the 'adapter gpio' syntax this script uses needs 0.12+." >&2
  echo "         On Raspberry Pi OS, use Bookworm (ships 0.12) or build OpenOCD 0.12 from source." >&2
fi

# The 40-pin header GPIOs live on the RP1 chip on a Pi 5 (gpiochip labelled 'pinctrl-rp1'); older
# Pis use 'pinctrl-bcm2835'. Auto-detect its gpiochip index unless GPIOCHIP is set explicitly.
detect_chip() {
  if [ -n "${GPIOCHIP:-}" ]; then echo "$GPIOCHIP"; return; fi
  if command -v gpiodetect >/dev/null 2>&1; then
    gpiodetect | awk '/rp1|bcm2835|bcm2711/{sub(/gpiochip/,"",$1); print $1; exit}'
  fi
}
CHIP="$(detect_chip)"; CHIP="${CHIP:-0}"
echo "Using gpiochip${CHIP}  SWDIO=GPIO${SWDIO_GPIO} (pin18)  SWCLK=GPIO${SWCLK_GPIO} (pin22)  speed=${SPEED_KHZ}kHz"
[ -n "$NRST_GPIO" ] && echo "NRST=GPIO${NRST_GPIO} (connect-under-reset enabled)"

# OpenOCD adapter preamble (modern 0.12 `adapter gpio` syntax). When a verified NRST line is given,
# enable connect-under-reset so the attach is reliable even against DISABLE_DEBUG firmware.
adapter_args=(
  -c "adapter driver linuxgpiod"
  -c "adapter gpio swclk -chip ${CHIP} ${SWCLK_GPIO}"
  -c "adapter gpio swdio -chip ${CHIP} ${SWDIO_GPIO}"
)
if [ -n "$NRST_GPIO" ]; then
  adapter_args+=(
    -c "adapter gpio srst -chip ${CHIP} ${NRST_GPIO}"
    -c "reset_config srst_only srst_nogate connect_assert_srst"
  )
fi
adapter_args+=(
  -c "transport select swd"
  -c "adapter speed ${SPEED_KHZ}"
  -f "target/stm32f1x.cfg"
)

cmd="${1:-probe}"
case "$cmd" in
  probe)
    # READ-ONLY: attach and report the core IDCODE + target — proves the wiring + power are right.
    # (Does NOT erase or write anything.) Times out if the stock firmware has disabled the SWD
    # port — that's the signal to use `recover`.
    openocd "${adapter_args[@]}" \
      -c "init" -c "dap info" -c "targets" -c "shutdown" 2>&1
    ;;
  unlock)
    # Clear read-out protection on an already-reachable chip (use after `probe` succeeds but `write`
    # fails on erase). Setting RDP 1->0 triggers a full mass erase; the new option bytes latch only
    # after a POWER CYCLE — so this exits and tells you to power-cycle.
    openocd "${adapter_args[@]}" \
      -c "init" -c "reset halt" \
      -c "stm32f1x unlock 0" \
      -c "shutdown" 2>&1 || true
    echo
    echo ">>> Now POWER-CYCLE the 4.2.2 (unplug/replug its power), then run:  ./flash-swd.sh write <fw.bin>"
    ;;
  recover)
    # Connect-under-power-cycle: defeats Marlin's DISABLE_DEBUG by catching the boot window before
    # the firmware reclaims PA13/PA14, then wiping it. Each attempt halts the core and erases —
    # `unlock` handles the read-protected case (RDP 1->0 auto-erases), `mass_erase` handles the
    # not-protected case; whichever doesn't apply is swallowed by Tcl `catch {}`, so the attempt
    # still succeeds. init/reset-halt are NOT caught: they only pass during the window, which is
    # exactly the gate we want.
    echo "CONNECT-UNDER-RESET recovery (no NRST needed)."
    echo ">>> POWER-CYCLE the board repeatedly (unplug/replug its power) while this loops."
    echo "    It grabs the brief boot window, then mass-erases the stock firmware + bootloader."
    i=0
    while [ "$i" -lt "$RETRIES" ]; do
      i=$((i + 1))
      if out="$(timeout 6 openocd "${adapter_args[@]}" \
                  -c "init" -c "reset halt" \
                  -c "catch {stm32f1x unlock 0}" \
                  -c "reset halt" \
                  -c "catch {stm32f1x mass_erase 0}" \
                  -c "reset run" -c "shutdown" 2>&1)"; then
        echo
        echo "  [attempt $i] CONNECTED + erased:"
        printf '%s\n' "$out" | sed 's/^/    /'
        echo
        echo ">>> SUCCESS. Now POWER-CYCLE the board ONCE more (to latch option bytes), then run:"
        echo "      ./flash-swd.sh write <fw.bin>"
        exit 0
      fi
      printf '\r  [attempt %d/%d] no connection yet — keep power-cycling…   ' "$i" "$RETRIES"
    done
    echo
    die "recover: exhausted $RETRIES attempts without catching the connect window.
     Try a slower clock (SPEED_KHZ=50), recheck the SWDIO/SWCLK/GND wiring, or — if you can
     identify and multimeter-verify a reset point — set NRST_GPIO=<pin> for connect-under-reset."
    ;;
  write)
    bin="${2:?usage: flash-swd.sh write <firmware.bin>}"
    [ -f "$bin" ] || die "firmware not found: $bin"
    openocd "${adapter_args[@]}" \
      -c "init" -c "reset halt" \
      -c "flash write_image erase ${bin} ${FLASH_ADDR}" \
      -c "verify_image ${bin} ${FLASH_ADDR}" \
      -c "reset run" \
      -c "shutdown"
    echo "OK: flashed + verified ${bin} at ${FLASH_ADDR}; board reset and running."
    ;;
  *)
    die "unknown command '${cmd}' — use: probe | unlock | recover | write <fw.bin>"
    ;;
esac
