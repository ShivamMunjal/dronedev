#!/usr/bin/env bash
# Populate IMU/Middlewares/MotionFX from an installed MEMS Studio.
#
# ST's MotionFX library is proprietary (SLA0077: free to use on STM32 parts, but
# not redistributable), so the binary is deliberately not committed to this repo.
# Run this once after cloning, or whenever MEMS Studio is updated.
set -euo pipefail
cd "$(dirname "$0")"

SRC="${MEMFX_SRC:-/Applications/MEMS Studio.app/Contents/Resources/ProjectTemplate/Middlewares/ST/STM32_MotionFX_Library}"

if [[ ! -d "$SRC" ]]; then
  echo "MEMS Studio MotionFX not found at:" >&2
  echo "  $SRC" >&2
  echo "Set MEMFX_SRC to override, or install MEMS Studio." >&2
  exit 1
fi

mkdir -p Middlewares/MotionFX/Inc Middlewares/MotionFX/Lib
cp "$SRC/Inc/motion_fx_cm0p.h" "$SRC/Inc/motion_fx.h" Middlewares/MotionFX/Inc/
cp "$SRC/Lib/MotionFX_CM0P_wc16_ot.a"              Middlewares/MotionFX/Lib/
cp "$SRC/Release_Notes.html"                       Middlewares/MotionFX/ 2>/dev/null || true

echo "MotionFX vendored into Middlewares/MotionFX:"
ls -l Middlewares/MotionFX/Inc Middlewares/MotionFX/Lib
echo
echo "NOTE: the .a is Cortex-M0+ code (MotionFX_CM0P_*). Licence SLA0077 -"
echo "      free on STM32 silicon, do not redistribute the binary."
