#!/bin/bash
# ─────────────────────────────────────────────────────────
# 🚁 EMAX Ground Station — Startup Script
# Connect NUCLEO-C092RC via USB-C, then run: ./start.sh
# ─────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   🚁 EMAX Ground Station                        ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# Check if NUCLEO is connected
if ls /dev/cu.usbmodem* 1>/dev/null 2>&1; then
    PORT=$(ls /dev/cu.usbmodem* | head -1)
    echo -e "${GREEN}✅ NUCLEO detected on $PORT${NC}"
else
    echo -e "${RED}❌ No NUCLEO found! Connect the board via USB-C first.${NC}"
    echo "   Waiting for device..."
    while ! ls /dev/cu.usbmodem* 1>/dev/null 2>&1; do sleep 1; done
    PORT=$(ls /dev/cu.usbmodem* | head -1)
    echo -e "${GREEN}✅ NUCLEO detected on $PORT${NC}"
fi

# Install deps if needed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# Kill any existing server on port 3000
lsof -ti:3000 | xargs kill 2>/dev/null || true
sleep 1

# Start server
echo ""
echo -e "${GREEN}🚀 Starting Ground Station...${NC}"
echo -e "   Open: ${CYAN}http://localhost:3000${NC}"
echo ""
echo "   Controls:"
echo "   • Click ARM → drag throttle slider → motor spins"
echo "   • Click DISARM or press Space → motor stops"
echo "   • Press Esc → emergency stop"
echo "   • Keyboard: ↑↓ = throttle, A = arm, D = disarm"
echo ""
echo "   Press Ctrl+C to stop the server."
echo "────────────────────────────────────────────────────"
echo ""

node server.js
