#!/usr/bin/env python3
"""
Drone 3D Dashboard — WebSocket Server
Reads real-time sensor data from SensorTile.box PRO and serves to browser.
"""
import os, sys, struct, time, math, json, asyncio, pathlib, signal
from threading import Thread

SDK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "external/stdatalog-pysdk")
sys.path.insert(0, SDK)
sys.path.insert(0, os.path.join(SDK, "stdatalog_core"))
sys.path.insert(0, os.path.join(SDK, "stdatalog_pnpl"))

from stdatalog_core.HSD_link.HSDLink import HSDLink, SensorAcquisitionThread

# WebSocket (websockets library)
try:
    import websockets
except ImportError:
    print("Installing websockets...")
    os.system(f"{sys.executable} -m pip install websockets")
    import websockets

# ── Shared sensor data (updated at 50Hz from USB) ──
sensor_data = {
    "acc": [0, 0, 0],
    "gyro": [0, 0, 0],
    "mag": [0, 0, 0],
    "press": 0,
    "temp": 0,
    "timestamp": 0,
}
sensor_lock = __import__("threading").Lock()

# ── Orientation state (complementary filter) ──
orientation = {"roll": 0, "pitch": 0, "yaw": 0, "altitude": 0}
ALTITUDE_OFFSET = None  # Calibrated on ground

# ── Decode params ──
decode_meta = {
    "lsm6dsv16x_acc":  {"dim":3,"sens":0.000488,"fmt":"h","sb":6},
    "lsm6dsv16x_gyro": {"dim":3,"sens":0.14,    "fmt":"h","sb":6},
    "lis2mdl_mag":     {"dim":3,"sens":0.0015,  "fmt":"h","sb":6},
    "lps22df_press":   {"dim":1,"sens":1.0,     "fmt":"f","sb":4},
    "stts22h_temp":    {"dim":1,"sens":1.0,     "fmt":"f","sb":4},
}

# ── Monkey-patch for real-time data ──
def patched_run(self):
    while not self.stopped.wait(0.02):  # 50Hz
        try:
            res = self.hsd_link.get_sensor_data(self.d_id, self.s_id, self.ss_id)
            if res is None: continue
            size, raw = res
            if not raw: continue
            if self.sensor_data_file: self.sensor_data_file.write(raw)

            m = decode_meta.get(self.s_id)
            if m:
                dim=m["dim"]; fmt=m["fmt"]; sens=m["sens"]; sb=m["sb"]
                n=len(raw)//sb
                if n>0:
                    off=(n-1)*sb
                    if fmt=='h':
                        v=struct.unpack_from("<"+"h"*dim,raw,off)
                        vals=[round(x*sens,4)for x in v]
                    else:
                        v=struct.unpack_from("<"+"f"*dim,raw,off)
                        vals=[round(x,2)for x in v]

                    with sensor_lock:
                        if "acc" in self.s_id:
                            sensor_data["acc"] = vals
                        elif "gyro" in self.s_id:
                            sensor_data["gyro"] = vals
                        elif "mag" in self.s_id:
                            sensor_data["mag"] = vals
                        elif "press" in self.s_id:
                            sensor_data["press"] = vals[0]
                        elif "temp" in self.s_id:
                            sensor_data["temp"] = vals[0]
                        sensor_data["timestamp"] = time.time()
        except:
            pass

SensorAcquisitionThread.run_no_print = patched_run

# ── Complementary filter for orientation ──
def update_orientation(dt):
    global ALTITUDE_OFFSET
    with sensor_lock:
        acc = list(sensor_data["acc"])
        gyro = list(sensor_data["gyro"])
        mag = list(sensor_data["mag"])
        press = sensor_data["press"]

    # Roll/Pitch from accelerometer
    ax, ay, az = acc
    roll_acc = math.atan2(ay, az) * 180 / math.pi
    pitch_acc = math.atan2(-ax, math.sqrt(ay*ay + az*az)) * 180 / math.pi

    # Yaw from magnetometer (tilt-compensated)
    mx, my, mz = mag
    roll_rad = orientation["roll"] * math.pi / 180
    pitch_rad = orientation["pitch"] * math.pi / 180
    mx2 = mx * math.cos(pitch_rad) + mz * math.sin(pitch_rad)
    my2 = mx * math.sin(roll_rad) * math.sin(pitch_rad) + my * math.cos(roll_rad) - mz * math.sin(roll_rad) * math.cos(pitch_rad)
    yaw_mag = math.atan2(-my2, mx2) * 180 / math.pi

    # Gyro integration
    gx, gy, gz = gyro  # dps

    # Complementary filter (0.98 gyro, 0.02 accel)
    alpha = 0.98
    orientation["roll"] = alpha * (orientation["roll"] + gx * dt) + (1 - alpha) * roll_acc
    orientation["pitch"] = alpha * (orientation["pitch"] + gy * dt) + (1 - alpha) * pitch_acc
    orientation["yaw"] = yaw_mag  # Magnetometer for yaw

    # Altitude from barometer (relative)
    if press > 0:
        # Barometric formula: h = 44330 * (1 - (P/P0)^(1/5.255))
        if ALTITUDE_OFFSET is None:
            ALTITUDE_OFFSET = press
        altitude = 44330.0 * (1.0 - pow(press / ALTITUDE_OFFSET, 1.0 / 5.255))
        orientation["altitude"] = round(altitude, 2)

# ── WebSocket handler ──
connected_clients = set()

async def ws_handler(websocket):
    connected_clients.add(websocket)
    print(f"Client connected ({len(connected_clients)} total)")
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get("type") == "calibrate":
                    global ALTITUDE_OFFSET
                    with sensor_lock:
                        ALTITUDE_OFFSET = sensor_data["press"]
                    await websocket.send(json.dumps({"type": "calibrated", "pressure": ALTITUDE_OFFSET}))
                elif data.get("type") == "get_config":
                    await websocket.send(json.dumps({
                        "type": "config",
                        "motors": ["M1","M2","M3","M4","M5","M6"],
                        "imu_placement": "front_right",
                    }))
            except json.JSONDecodeError:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.discard(websocket)
        print(f"Client disconnected ({len(connected_clients)} total)")

async def broadcast_sensor_data():
    """Send sensor data to all connected clients at 30Hz."""
    last_time = time.time()
    while True:
        now = time.time()
        dt = now - last_time
        last_time = now

        # Update orientation
        update_orientation(dt)

        # Prepare data
        with sensor_lock:
            msg = json.dumps({
                "type": "sensor",
                "acc": sensor_data["acc"],
                "gyro": sensor_data["gyro"],
                "mag": sensor_data["mag"],
                "press": sensor_data["press"],
                "temp": sensor_data["temp"],
                "roll": round(orientation["roll"], 2),
                "pitch": round(orientation["pitch"], 2),
                "yaw": round(orientation["yaw"], 2),
                "altitude": orientation["altitude"],
                "timestamp": sensor_data["timestamp"],
            })

        # Broadcast
        if connected_clients:
            await asyncio.gather(
                *[client.send(msg) for client in connected_clients],
                return_exceptions=True
            )

        await asyncio.sleep(0.033)  # 30Hz

# ── Main ──
def start_sensor_thread():
    """Start SensorTile.box PRO streaming in background."""
    global sensor_data

    print("Connecting to SensorTile.box PRO...", flush=True)
    try:
        hsd_link = HSDLink()
        hsd = hsd_link.create_hsd_link(dev_com_type="st_hsd", acquisition_folder="live_capture")
        if not hsd:
            print("Failed to connect to SensorTile.box PRO", flush=True)
            return None
    except Exception as e:
        print(f"Connection error: {e}", flush=True)
        return None

    did = 0
    try:
        names = HSDLink.get_sensors_names(hsd, did, only_active=True)
        print(f"Active sensors: {', '.join(names)}", flush=True)
    except Exception as e:
        print(f"Error getting sensors: {e}", flush=True)
        # Use hardcoded names as fallback
        names = ["lsm6dsv16x_acc", "lsm6dsv16x_gyro", "lis2mdl_mag", "lps22df_press", "stts22h_temp"]
        print(f"Using fallback sensors: {', '.join(names)}", flush=True)

    sf = []; fl = []
    for s in names:
        try:
            HSDLink.start_sensor_acquisition_thread(hsd, did, s, sf, fl, print_data_cnt=False)
        except Exception as e:
            print(f"Error starting thread for {s}: {e}", flush=True)
    HSDLink.start_log(hsd, did, interface=1)
    print("Sensor streaming started", flush=True)

    return hsd, sf, fl

async def main():
    # Start sensor thread
    sensor_thread = Thread(target=start_sensor_thread, daemon=True)
    sensor_thread.start()

    # Wait for sensor to connect
    await asyncio.sleep(3)

    # Start WebSocket server
    print("Starting WebSocket server on ws://0.0.0.0:8765", flush=True)
    async with websockets.serve(ws_handler, "0.0.0.0", 8765):
        print("Dashboard ready at http://localhost:8080", flush=True)
        print("Open http://localhost:8080 in browser", flush=True)
        await broadcast_sensor_data()

if __name__ == "__main__":
    asyncio.run(main())
