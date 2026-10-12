#!/usr/bin/env bash
# Build the PM02D telemetry firmware for NUCLEO-C092RC (STM32C092RC).
set -euo pipefail
cd "$(dirname "$0")"

CLT="${STM32_CUBECLT:-/opt/ST/STM32CubeCLT_1.22.0}"
if [[ -d "$CLT/CMake/bin" ]]; then
  export PATH="$CLT/CMake/bin:$CLT/Ninja/bin:$CLT/GNU-tools-for-STM32/bin:$PATH"
fi

command -v arm-none-eabi-gcc >/dev/null || { echo "arm-none-eabi-gcc not found"; exit 1; }

cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build

echo
ls -l build/imu_ism330is_c092rc.elf build/imu_ism330is_c092rc.hex build/imu_ism330is_c092rc.bin
