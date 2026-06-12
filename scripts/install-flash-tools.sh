#!/usr/bin/env bash
# Install the host-side flashing tools the PiBot Control Suite drives:
#   - rpi-imager  (Raspberry Pi Imager — writes OS images)
#   - rpiboot     (from raspberrypi/usbboot — puts a Pi 5 into mass-storage mode)
# Idempotent: re-running skips anything already present. macOS-focused; on Linux
# rpi-imager and rpiboot are available via the distro package manager.
set -euo pipefail

CACHE="${HOME}/.cache/pibot"
USBBOOT_DIR="${CACHE}/usbboot"
IMAGER_APP="/Applications/Raspberry Pi Imager.app/Contents/MacOS/rpi-imager"

echo "== rpi-imager =="
if command -v rpi-imager >/dev/null 2>&1 || [ -x "${IMAGER_APP}" ]; then
  echo "rpi-imager already installed"
elif command -v brew >/dev/null 2>&1; then
  brew install --cask raspberry-pi-imager
else
  echo "Homebrew not found — install rpi-imager from https://www.raspberrypi.com/software/" >&2
  exit 1
fi

echo ""
echo "== rpiboot (raspberrypi/usbboot) =="
if [ -x "${USBBOOT_DIR}/rpiboot" ]; then
  echo "rpiboot already built at ${USBBOOT_DIR}/rpiboot"
else
  command -v pkg-config >/dev/null 2>&1 || brew install pkgconf
  brew list --versions libusb >/dev/null 2>&1 || brew install libusb
  mkdir -p "${CACHE}"
  if [ ! -d "${USBBOOT_DIR}/.git" ]; then
    git clone --depth 1 https://github.com/raspberrypi/usbboot "${USBBOOT_DIR}"
  fi
  make -C "${USBBOOT_DIR}"
fi

echo ""
echo "rpiboot:     ${USBBOOT_DIR}/rpiboot"
echo "rpi-imager:  ${IMAGER_APP}"
echo "Done. The suite resolves both via pibot.provision.tools."
