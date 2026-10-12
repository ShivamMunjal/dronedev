#!/usr/bin/env bash
# Flash over SWD using the on-board ST-LINK of the NUCLEO-C092RC.
set -euo pipefail
cd "$(dirname "$0")"

CLT="${STM32_CUBECLT:-/opt/ST/STM32CubeCLT_1.22.0}"
PROG="$CLT/STM32CubeProgrammer/bin/STM32_Programmer_CLI"

[[ -f build/imu_ism330is_c092rc.elf ]] || { echo "Build first: ./build.sh"; exit 1; }

if [[ -x "$PROG" ]]; then
  "$PROG" -c port=SWD mode=UR -w build/imu_ism330is_c092rc.elf -v -rst
else
  st-flash --reset write build/imu_ism330is_c092rc.bin 0x08000000
fi
