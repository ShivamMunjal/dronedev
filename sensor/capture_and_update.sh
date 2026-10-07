#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# SensorTile.box PRO — Capture IMU + Mag + Pressure & Update Dashboard
# Usage: ./capture_and_update.sh [duration_seconds]
# Default: 10 seconds
# ─────────────────────────────────────────────────────────────────
set -e

SENSOR_DIR="$(cd "$(dirname "$0")" && pwd)"
CLI="$SENSOR_DIR/external/fp-sns-datalog2/Utilities/cli_example/bin_macos/arm64/cli_example"
CONFIG="$SENSOR_DIR/imu_mag_press.json"
DURATION="${1:-10}"

export DYLD_LIBRARY_PATH="$(dirname "$CLI"):${DYLD_LIBRARY_PATH:-}"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  SensorTile.box PRO — IMU + Mag + Pressure Capture     ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Board:    STEVAL-MKBOXPRO (STM32U585AI)               ║"
echo "║  Sensors:  LSM6DSV16X (acc+gyro), LIS2MDL, LPS22DF     ║"
echo "║  Duration: ${DURATION}s                                        ║"
echo "║  USB:      0483:5744 WinUSB                             ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Check board
if ! ioreg -p IOUSB -w0 2>/dev/null | grep -q "Sensortile"; then
    echo "❌ SensorTile.box PRO not detected on USB!"
    echo "   → Make sure box is ON and connected via USB-C data cable"
    echo "   → Try: ioreg -p IOUSB | grep Sensortile"
    exit 1
fi

echo "✅ Board detected"
echo "📡 Capturing for ${DURATION}s..."
echo ""

# Capture
cd "$SENSOR_DIR/external/fp-sns-datalog2/Utilities/cli_example"
"$CLI" -f "$CONFIG" -t "$DURATION" -y 2>&1 | tail -n 20

# Find newest acquisition folder
NEWEST=$(ls -td 2*_*/ 2>/dev/null | head -n 1)
if [ -z "$NEWEST" ]; then
    echo "❌ No acquisition folder found"
    exit 1
fi

echo ""
echo "📁 Captured: $NEWEST"
ls -lh "$NEWEST"/*.dat 2>/dev/null

# Copy to captures
mkdir -p "$SENSOR_DIR/captures"
cp -r "$NEWEST" "$SENSOR_DIR/captures/"

# Decode and update dashboard data
echo ""
echo "🔄 Decoding sensor data..."
python3 << PYEOF
import pathlib, struct, json

base = pathlib.Path("$PWD/$NEWEST")
dc = json.loads((base/"device_config.json").read_text())
ai = json.loads((base/"acquisition_info.json").read_text())

comp_cfg = {}
for dev in dc["devices"]:
    for c in dev["components"]:
        for k,v in c.items():
            if isinstance(v, dict) and "data_type" in v:
                comp_cfg[k] = v

def decode_hsd2(path, cfg):
    raw = path.read_bytes()
    dtype = cfg["data_type"]
    dim = cfg["dim"]
    sens = cfg.get("sensitivity", 1.0)
    b_per = 2 if dtype == "int16" else 4 if dtype in ("float", "float_t") else 1
    sample_bytes = b_per * dim
    off = 0
    all_samples = []
    while off + 4 <= len(raw):
        chunk_size = struct.unpack_from("<I", raw, off)[0]
        off += 4
        if chunk_size == 0:
            # v3.3.0: chunk_size=0 means rest of file is raw packed samples
            payload = raw[off:]
            n = len(payload) // sample_bytes
            for i in range(n):
                boff = i * sample_bytes
                if dtype == "int16":
                    vals = list(struct.unpack_from("<" + "h" * dim, payload, boff))
                    vals = [round(v * sens, 6) for v in vals]
                elif dtype in ("float", "float_t"):
                    vals = list(struct.unpack_from("<" + "f" * dim, payload, boff))
                    vals = [round(v, 4) for v in vals]
                else:
                    vals = [0]
                all_samples.append(vals if dim > 1 else vals[0])
            break
        else:
            if off + chunk_size > len(raw):
                break
            payload = raw[off:off+chunk_size]
            off += chunk_size
            n = chunk_size // sample_bytes
            for i in range(n):
                boff = i * sample_bytes
                if dtype == "int16":
                    vals = list(struct.unpack_from("<" + "h" * dim, payload, boff))
                    vals = [round(v * sens, 6) for v in vals]
                elif dtype in ("float", "float_t"):
                    vals = list(struct.unpack_from("<" + "f" * dim, payload, boff))
                    vals = [round(v, 4) for v in vals]
                else:
                    vals = [0]
                all_samples.append(vals if dim > 1 else vals[0])
    return all_samples

sensors = {}
for name in ["lsm6dsv16x_acc", "lsm6dsv16x_gyro", "lis2mdl_mag", "lps22df_press", "stts22h_temp", "lis2du12_acc"]:
    p = base / (name + ".dat")
    if p.exists() and name in comp_cfg:
        samples = decode_hsd2(p, comp_cfg[name])
        sensors[name] = {"samples": samples, "config": comp_cfg[name], "count": len(samples)}
        print(f"  {name}: {len(samples)} samples")

dashboard_data = {"acquisition_info": ai, "sensors": {}}
for name, s in sensors.items():
    cfg = s["config"]
    samples = s["samples"][:5000]
    dashboard_data["sensors"][name] = {
        "count": s["count"], "dim": cfg["dim"], "data_type": cfg["data_type"],
        "odr": cfg.get("measodr", cfg.get("odr")), "unit": "",
        "sensitivity": cfg.get("sensitivity"), "samples": samples
    }
    if "acc" in name:
        dashboard_data["sensors"][name]["unit"] = "g"
        dashboard_data["sensors"][name]["labels"] = ["X", "Y", "Z"]
    elif "gyro" in name:
        dashboard_data["sensors"][name]["unit"] = "dps"
        dashboard_data["sensors"][name]["labels"] = ["X", "Y", "Z"]
    elif "mag" in name:
        dashboard_data["sensors"][name]["unit"] = "Gauss"
        dashboard_data["sensors"][name]["labels"] = ["X", "Y", "Z"]
    elif "press" in name:
        dashboard_data["sensors"][name]["unit"] = "hPa"
        dashboard_data["sensors"][name]["labels"] = ["Pressure"]
    elif "temp" in name:
        dashboard_data["sensors"][name]["unit"] = "°C"
        dashboard_data["sensors"][name]["labels"] = ["Temperature"]

out = pathlib.Path("$SENSOR_DIR/dashboard_data.json")
out.write_text(json.dumps(dashboard_data, separators=(',', ':')))
print(f"\n✅ Dashboard data updated: {out} ({out.stat().st_size} bytes)")
PYEOF

# Embed data into HTML (file:// can't fetch JSON)
echo ""
echo "📊 Embedding data into dashboard..."
python3 << 'EMBED'
import json, pathlib, re
html_path = pathlib.Path("$SENSOR_DIR/dashboard.html")
data_path = pathlib.Path("$SENSOR_DIR/dashboard_data.json")
html = html_path.read_text()
data = data_path.read_text()
html = re.sub(r'const __DATA = \{.*?\};\nconst data = __DATA;', 'const __DATA = ' + data + ';\nconst data = __DATA;', html, flags=re.DOTALL)
html_path.write_text(html)
print(f"  Embedded {len(data)} bytes into HTML")
EMBED

echo ""
echo "🌐 Opening dashboard..."
open "$SENSOR_DIR/dashboard.html"
echo "✅ Done!"
