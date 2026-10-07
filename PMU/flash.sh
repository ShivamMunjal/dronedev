#!/usr/bin/env bash
# Flash the firmware over SWD using ST-Link (works with the USB cable you
# already have plugged into the Nucleo - no BOOT0 jumper needed).
set -euo pipefail
cd "$(dirname "$0")"

CLT="${STM32_CUBECLT:-/opt/ST/STM32CubeCLT_1.22.0}"
PROG="$CLT/STM32CubeProgrammer/bin/STM32_Programmer_CLI"

[[ -f build/pmu_pm02d.elf ]] || { echo "Build first: ./build.sh"; exit 1; }

if [[ -x "$PROG" ]]; then
  "$PROG" -c port=SWD mode=UR -w build/pmu_pm02d.elf -v -rst
else
  st-flash --reset write build/pmu_pm02d.bin 0x08000000
fi
