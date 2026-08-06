#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "╔══════════════════════════════════════════════════╗"
echo "║   🚁 MultiMotor Ground Station (6 ESCs)         ║"
echo "╚══════════════════════════════════════════════════╝"
if ! ls /dev/cu.usbmodem* 1>/dev/null 2>&1; then
  echo "❌ No NUCLEO found! Connect via USB-C first."
  echo "   Waiting for device..."
  while ! ls /dev/cu.usbmodem* 1>/dev/null 2>&1; do sleep 1; done
fi
echo "✅ NUCLEO detected on $(ls /dev/cu.usbmodem* | head -1)"
[ ! -d node_modules ] && npm install
lsof -ti:3000 | xargs kill 2>/dev/null || true
sleep 1
echo "🚀 Starting server → http://localhost:3000"
echo ""
node server.js
