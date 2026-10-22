#!/bin/bash
# Launch the IMU attitude dashboard (MotionFX 6X) on the NUCLEO-C092RC.
set -e
cd "$(dirname "$0")"
echo "╔══════════════════════════════════════════════╗"
echo "║   🧭 IMU Ground Station (MotionFX 6X)       ║"
echo "╚══════════════════════════════════════════════╝"
if ! ls /dev/cu.usbmodem* >/dev/null 2>&1; then
  echo "❌ No NUCLEO found. Plug the board in via USB-C."
  echo "   Waiting for device..."
  while ! ls /dev/cu.usbmodem* >/dev/null 2>&1; do sleep 1; done
fi
echo "✅ NUCLEO detected on $(ls /dev/cu.usbmodem* | head -1)"
[ ! -d node_modules ] && npm install
lsof -ti:4100 | xargs kill 2>/dev/null || true
sleep 1
echo "🚀 Starting server → http://localhost:4100"
echo ""
node server.js
