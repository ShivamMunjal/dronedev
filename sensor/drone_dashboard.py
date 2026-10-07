#!/usr/bin/env python3
"""
Hexacopter 3D Dashboard — TRUE REALTIME via direct USB streaming.

Uses ST's official DataReader (stdatalog-pysdk) fed by get_sensor_data() polling,
same as ST's own stdatalog_sensors_streaming example. No .dat file polling.

spts tuned for low latency: acc/gyro 20 (~10ms frames), mag 5, press 1.
Serves drone_3d.html on :8080, /api/sensor polled by browser at 30Hz.
"""
import os, sys, struct, time, json, math, threading, pathlib
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from mixer import HexaMixer, motor_command_line

MIXER = HexaMixer()

PORT = 8080
BASE = pathlib.Path(__file__).parent

SDK = str(BASE / "external/stdatalog-pysdk")
sys.path.insert(0, SDK)
sys.path.insert(0, os.path.join(SDK, "stdatalog_core"))
sys.path.insert(0, os.path.join(SDK, "stdatalog_pnpl"))

from stdatalog_core.HSD_link.HSDLink import HSDLink
from stdatalog_core.HSD_utils.DataReader import DataReader
from stdatalog_core.HSD.utils.type_conversion import TypeConversion

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fusion
from fusion import MahonyAHRS, MagCalibration, wrap180

# Wire spts — device default 1000 (custom set is NOT honored reliably,
# it reports the new value but keeps framing at 1000 -> misaligned samples
# and |acc| ~0.6g instead of 1.0g). Keep 1000 until FW framing is verified.
SPTS = {"lsm6dsv16x_acc": 1000, "lsm6dsv16x_gyro": 1000,
        "lis2mdl_mag": 100, "lps22df_press": 200}

# Airframe mounting of the SensorTile (see the remap block in the fusion loop).
# Default = box-top-up, axes aligned with the airframe.
#   upside down on the frame        -> AXIS_SIGN = (1, 1, -1)
#   rotated 90deg about the z axis  -> AXIS_ORDER = (1, 0, 2); AXIS_SIGN = (-1, 1, 1)
AXIS_ORDER = (0, 1, 2)
AXIS_SIGN = (1, 1, 1)

# Mounting rotation, driven by the "USB Cable ->" selector in the dashboard.
# A flat-mounted IMU can only be rotated about its z (up) axis, so every option
# is a 90 deg step: that is a pure axis permutation + sign flip, which is exactly
# what AXIS_ORDER/AXIS_SIGN express.  "right" is the bench-validated default.
#   theta = 0    -> identity
#   theta = 90   -> order (1,0,2), sign ( 1,-1,1)
#   theta = 180  -> order (0,1,2), sign (-1,-1,1)
#   theta = 270  -> order (1,0,2), sign (-1, 1,1)
CABLE_MOUNT = {
    "right": {"theta": 0.0,   "order": (0, 1, 2), "sign": (1, 1, 1)},
    "back":  {"theta": 180.0, "order": (0, 1, 2), "sign": (-1, -1, 1)},
    "left":  {"theta": 90.0,  "order": (1, 0, 2), "sign": (1, -1, 1)},
    "front": {"theta": 270.0, "order": (1, 0, 2), "sign": (-1, 1, 1)},
}
MOUNT = {"cable": "right", "imu_pos": "center", "theta": 0.0}

# ── Attitude estimation ─────────────────────────────────────────
# The filter itself lives in fusion.py (Mahony AHRS, PX4-style, with
# ArduPilot-style magnetometer gating).  Tune KP_ACC / KP_MAG / KI_BIAS there.
# The old EMA / deadband / yaw-slew knobs are gone on purpose: they were the
# cause of the lag (a 0.40 dps deadband discarded slow rotation entirely).
PRESS_LP = 0.20      # baro EMA
MAGCAL_PATH = pathlib.Path(__file__).parent / "magcal.json"

sensor_data = {"roll":0,"pitch":0,"yaw":0,"altitude":0,"acc":[0,0,0],"gyro":[0,0,0],"mag":[0,0,0],"press":0,"temp":25,"timestamp":0}
lock = threading.Lock()
alt_offset = None
trim = [0.0, 0.0]   # roll/pitch level trim (deg), set by /api/trim
filt = MahonyAHRS()
magc = MagCalibration.load(MAGCAL_PATH)
magcal_collecting = False
magcal_last = ""

# latest decoded samples from DataReader callbacks
latest = {}
latest_lock = threading.Lock()
cb_counts = {}
cb_errors = {}

def make_cb(comp_name):
    def cb(dc):
        try:
            d = dc.data
            if isinstance(d, dict):
                # DataReader emits {channel: np.ndarray}
                vals = None
                if len(d) == 1:
                    arr = list(d.values())[0]
                    vals = [float(x) for x in arr[-1:]] if len(arr) else None
                else:
                    chs = sorted(d.keys())
                    vals = [float(d[c][-1]) for c in chs]
                if vals:
                    with latest_lock:
                        latest[comp_name] = vals
                        cb_counts[comp_name] = cb_counts.get(comp_name, 0) + 1
        except Exception as e:
            with latest_lock:
                cb_errors[comp_name] = str(e)[:120]
    return cb

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        global alt_offset
        path = urlparse(self.path).path
        if path in ("/","/index.html","/drone_3d.html"):
            self.send_response(200)
            self.send_header("Content-Type","text/html")
            self.end_headers()
            self.wfile.write((BASE/"drone_3d.html").read_bytes())
        elif path == "/api/sensor":
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Access-Control-Allow-Origin","*")
            self.end_headers()
            with lock:
                self.wfile.write(json.dumps(sensor_data).encode())
        elif path == "/api/calibrate":
            with lock:
                alt_offset = None
                sensor_data["altitude"] = 0
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        elif path == "/api/mixer":
            # IMU -> mixer-ready. Query: ?throttle=0.45&roll=0&pitch=0&yaw=0
            q = parse_qs(urlparse(self.path).query)
            def _f(k, dflt):
                try: return float(q.get(k, [dflt])[0])
                except Exception: return dflt
            with lock:
                sd = dict(sensor_data)
            gyro = sd.get("gyro", [0.0, 0.0, 0.0])
            thr = _f("throttle", 0.0)
            pwms = MIXER.mix(thr, _f("roll", 0.0), _f("pitch", 0.0), _f("yaw", 0.0))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "src": "sensorbox", "timestamp": sd.get("timestamp", 0),
                "roll": sd.get("roll", 0.0), "pitch": sd.get("pitch", 0.0),
                "yaw": sd.get("yaw", 0.0),
                # body rates (deg/s) = the actual control input for the mixer
                "rate": {"p": gyro[0], "q": gyro[1], "r": gyro[2]},
                "acc": sd.get("acc", [0, 0, 0]), "mag": sd.get("mag", [0, 0, 0]),
                "altitude": sd.get("altitude", 0.0), "press": sd.get("press", 0.0),
                # mixer output (us, motor 1..6)
                "mixer": {"geometry": "hexa-X", "throttle": thr,
                          "motors": [{"id": i + 1, "pwm": p} for i, p in enumerate(pwms)],
                          "uart": motor_command_line(pwms, sep=" ", trailing=False),
                          "uart_lines": motor_command_line(pwms)},
            }).encode())
        elif path == "/api/trim":
            # Capture the current attitude as the new "level" reference.
            # Lay the box flat, then hit this so the model reads 0/0.
            with lock:
                trim[0] = (trim[0] + sensor_data.get("roll", 0.0)) % 360
                if trim[0] > 180: trim[0] -= 360
                trim[1] = trim[1] + sensor_data.get("pitch", 0.0)
                # re-zero the published values immediately
                sensor_data["roll"] = 0.0
                sensor_data["pitch"] = 0.0
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "trim_roll": round(trim[0],2),
                                         "trim_pitch": round(trim[1],2)}).encode())
        elif path == "/api/mount":
            # Declare how the box sits on the airframe.
            #   ?cable=front|back|left|right   (which way the USB cable points)
            #   ?imu=center|front|left|...     (where on the frame it is mounted)
            # The cable direction sets the yaw rotation applied to every IMU
            # reading before fusion.  The imu position is recorded for reference
            # only -- a flat-mounted IMU's position does not affect attitude.
            q = parse_qs(urlparse(self.path).query)
            cable = (q.get("cable", [""])[0] or "").lower()
            imu = (q.get("imu", [""])[0] or "").lower()
            if cable:
                if cable not in CABLE_MOUNT:
                    self.send_response(400); self.send_header("Content-Type","application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": False,
                        "error": f"cable must be one of {list(CABLE_MOUNT)}"}).encode())
                    return
                MOUNT["cable"] = cable
                MOUNT["theta"] = CABLE_MOUNT[cable]["theta"]
                filt._mag_locked = False          # heading reference moved
            if imu:
                MOUNT["imu_pos"] = imu
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "mount": MOUNT,
                "order": list(CABLE_MOUNT[MOUNT["cable"]]["order"]),
                "sign": list(CABLE_MOUNT[MOUNT["cable"]]["sign"])}).encode())
        elif path == "/api/magcal":
            # Magnetometer calibration: hard-iron offset + soft-iron scale.
            #   /api/magcal?cmd=start  -> begin collecting (slowly rotate the box)
            #   /api/magcal?cmd=fit    -> fit + save, then reset the health ref
            #   /api/magcal?cmd=cancel -> abort
            #   /api/magcal            -> status
            global magcal_collecting, magcal_last
            q = parse_qs(urlparse(self.path).query)
            cmd = (q.get("cmd", [""])[0] or "").lower()
            if cmd == "start":
                magc._min = [1e9] * 3
                magc._max = [-1e9] * 3
                magc._n = 0
                magcal_collecting = True
                magcal_last = "collecting — rotate the box slowly through all orientations"
                result = {"ok": True, "state": "collecting", "msg": magcal_last}
            elif cmd == "cancel":
                magcal_collecting = False
                magcal_last = "cancelled"
                result = {"ok": True, "state": "cancelled"}
            elif cmd == "fit":
                magcal_collecting = False
                ok, msg = magc.fit()
                magcal_last = msg
                if ok:
                    magc.save(MAGCAL_PATH)
                    filt.health.ref_len = None      # re-learn the field length
                result = {"ok": ok, "state": "fitted" if ok else "failed",
                          "msg": msg, "samples": magc.samples,
                          "cal": magc.to_dict()}
            else:
                result = {"collecting": magcal_collecting,
                          "samples": magc.samples, "last": magcal_last,
                          "cal": magc.to_dict()}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif path == "/api/diag":
            with latest_lock:
                c = dict(cb_counts); e = dict(cb_errors)
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"cb_counts": c, "cb_errors": e,
                                         "age": round(time.time() - sensor_data.get("timestamp", 0), 2),
                                         "trim": [round(trim[0],2), round(trim[1],2)],
                                         "fusion": filt.status(), "mount": MOUNT}).encode())
        else:
            self.send_response(404)
            self.end_headers()

class DC:
    def __init__(self, comp_name, data):
        self.comp_name = comp_name
        self.data = data

_stop_done = {"v": False}

def safe_stop(hsd):
    """Stop the FW log exactly once (idempotent — it is called from both the
    signal handler and atexit). Calling stop_log twice on a live link is what
    can leave the log engine in a bad state."""
    if _stop_done["v"]:
        return
    _stop_done["v"] = True
    try:
        HSDLink.stop_log(hsd, 0)
        print("clean stop_log on exit", flush=True)
    except Exception:
        pass

def stream_thread(hsd, comp_name, usb_dps, reader, stop_ev):
    span = usb_dps + 4
    while not stop_ev.is_set():
        try:
            res = hsd.get_sensor_data(0, comp_name)
        except Exception:
            time.sleep(0.05)
            continue
        if res is None:
            time.sleep(0.002)
            continue
        _, blob = res
        if not blob:
            continue
        n = len(blob) // span
        for i in range(n):
            base = i * span
            payload = bytes(blob[base+4:base+span])
            try:
                reader.feed_data(DC(comp_name, payload))
            except Exception:
                pass

def open_link():
    h = HSDLink()
    return h.create_hsd_link(dev_com_type="st_hsd", acquisition_folder="live_capture")

def poll_any_data(hsd, comps, secs=1.0):
    """True if any sensor yields bytes within secs. Never aborts."""
    t_end = time.time() + secs
    while time.time() < t_end:
        for name in comps:
            try:
                res = hsd.get_sensor_data(0, name)
            except Exception:
                continue
            if res is not None and res[0] > 0:
                return True
        time.sleep(0.02)
    return False

def acc_magnitude_ok(timeout=4.0):
    """Check fused acc ≈1g (validates spts match)."""
    t_end = time.time() + timeout
    while time.time() < t_end:
        with lock:
            a = list(sensor_data["acc"])
        m = math.sqrt(sum(x*x for x in a))
        if 0.8 < m < 1.2:
            return True
        time.sleep(0.2)
    return False

def sensor_loop():
    global sensor_data, alt_offset
    import atexit
    print("Connecting to SensorTile.box PRO...", flush=True)
    hsd = open_link()
    if not hsd:
        print("FAILED to connect — retry in 5s", flush=True)
        time.sleep(5)
        return sensor_loop()
    atexit.register(lambda: safe_stop(hsd))
    globals()["_hsd"] = hsd  # for the main-thread signal handler

    # NOTE: do NOT push custom spts — device acks it but keeps wire framing,
    # which desyncs DataReader (|acc| wrong). Use device defaults.
    # (Set SPTS above to match device_config.json / verified framing.)

    status = hsd.get_device_status(0)
    comps = {}
    for comp in status["devices"][0]["components"]:
        name = next(iter(comp)); st = comp[name]
        if st.get("c_type") == 0 and st.get("enable"):  # SENSOR=0
            comps[name] = st
    print("streaming:", ", ".join(comps), flush=True)
    # actual spts on wire (FW may ignore set) — DataReader must match wire
    wire_spts = {}
    for name in SPTS:
        try:
            v = hsd.get_sensor_samples_per_ts(0, name)
            wire_spts[name] = v if v else SPTS[name]
        except Exception:
            wire_spts[name] = SPTS[name]
    print(f"wire spts: {wire_spts}", flush=True)

    time.sleep(1.0)  # let USB settle (avoids Abort trap)
    # NOTE: never call start/stop_log here — FW wedges on stop->start in one
    # process (native SIGABRT) and lies about log state. Board was power-cycled
    # clean; just probe and attach, or start once if proven idle.
    flowing = poll_any_data(hsd, SPTS.keys(), secs=2.0)
    print(f"board already streaming: {flowing}", flush=True)
    if not flowing:
        HSDLink.start_log(hsd, 0, interface=1)  # proven idle: safe
        print("start_log sent", flush=True)
        time.sleep(0.5)
    else:
        print("ATTACH mode (no start_log)", flush=True)
    print("LIVE streaming", flush=True)

    stop_ev = threading.Event()
    readers = {}
    for name, st in comps.items():
        if name not in SPTS:
            continue
        dim = st.get("dim", 1)
        sens = st.get("sensitivity", 1.0)
        spts = wire_spts.get(name, SPTS[name])
        dtype = st.get("data_type", "int16")
        readers[name] = DataReader(
            make_cb(name), name, spts, dim,
            TypeConversion.check_type_length(dtype),
            TypeConversion.get_format_char(dtype),
            sens, True, False)
        usb_dps = st.get("usb_dps", 0)
        t = threading.Thread(target=stream_thread,
                             args=(hsd, name, usb_dps, readers[name], stop_ev),
                             daemon=True)
        t.start()

    def wrap180(a):
        while a > 180: a -= 360
        while a < -180: a += 360
        return a

    press_f = None
    t_last = time.time()
    while True:
        now = time.time()
        dt = min(max(now - t_last, 0.001), 0.2)
        t_last = now
        with latest_lock:
            snap = dict(latest)
        acc_raw = snap.get("lsm6dsv16x_acc")
        gyr_raw = snap.get("lsm6dsv16x_gyro")
        mag_raw = snap.get("lis2mdl_mag")
        prs = snap.get("lps22df_press")

        # ── Mounting orientation ────────────────────────────────────────
        # Remap the box's IMU axes onto the airframe. Lay the box flat with its
        # top up: correct mounting reads az ~= +1.0g, roll ~= 0, pitch ~= 0.
        # If az ~= -1.0g / roll ~= 180, the box is upside down -> flip Z below.
        # `order` permutes axes (sensor idx -> body pos); `sign` flips each one.
        _m = CABLE_MOUNT[MOUNT["cable"]]
        _order, _sign = _m["order"], _m["sign"]
        if _order != (0, 1, 2) or _sign != (1, 1, 1):
            def _remap(v):
                return [_sign[i] * v[_order[i]] for i in range(3)]
            if acc_raw and len(acc_raw) == 3: acc_raw = _remap(acc_raw)
            if gyr_raw and len(gyr_raw) == 3: gyr_raw = _remap(gyr_raw)
            if mag_raw and len(mag_raw) == 3: mag_raw = _remap(mag_raw)

        # ── magnetometer: hard-iron calibration, then gating ───────────────
        mag_cal = None
        if mag_raw and len(mag_raw) == 3:
            if magcal_collecting:
                magc.add(mag_raw)
            mag_cal = magc.apply(mag_raw)

        # ── Mahony AHRS (PX4-style): gyro-led, accel + mag gated ───────────
        # Gyro is integrated with NO deadband -> no lag.
        # Accel corrects roll/pitch only when |a| is in [0.85, 1.15] g.
        # Mag corrects heading only while the field looks healthy; otherwise the
        # filter coasts on gyro, so waving metal near the box does not move yaw.
        gyro_dps = list(gyr_raw[:3]) if (gyr_raw and len(gyr_raw) == 3) else [0.0, 0.0, 0.0]
        accel_g  = list(acc_raw[:3]) if (acc_raw and len(acc_raw) == 3) else None
        roll, pitch, yaw = filt.update(gyro_dps, accel_g, mag_cal, dt)
        gx, gy, gz = gyro_dps
        acc_f = accel_g
        mag_f = mag_cal

        # baro EMA
        alt = sensor_data["altitude"]
        press = press_f or 0
        if prs and len(prs) >= 1 and 100 < prs[0] < 1500:
            press_f = prs[0] if press_f is None else press_f + PRESS_LP*(prs[0]-press_f)
            press = press_f
            if alt_offset is None:
                alt_offset = press_f
            alt = round(44330*(1-pow(press_f/alt_offset, 1/5.255)), 2)

        with lock:
            sensor_data.update({
                "roll": round(wrap180(roll - trim[0]), 2),
                "pitch": round(pitch - trim[1], 2),
                "yaw": round(yaw,2), "altitude": alt,
                "acc": [round(x,4) for x in acc_f] if acc_f else [0,0,0],
                "gyro": [round(gx,2), round(gy,2), round(gz,2)],
                "mag": [round(x,4) for x in mag_f] if mag_f else [0,0,0],
                "press": round(press,2),
                "timestamp": time.time(),
            })
        time.sleep(0.033)  # 30Hz fusion output

if __name__ == "__main__":
    # kill -9 BYPASSES atexit and leaves the FW log engine WEDGED (only a full
    # power-cycle clears it). Register graceful TERM/INT handlers in the MAIN
    # thread so `pkill -TERM -f drone_dashboard` always stops the log cleanly.
    # (signal.signal() raises ValueError if called from a worker thread.)
    import signal
    _fired = {"v": False}
    def _graceful(signum, _frame):
        if _fired["v"]:
            return
        _fired["v"] = True
        print(f"\nsignal {signum}: stopping cleanly...", flush=True)
        h = globals().get("_hsd")
        if h:
            safe_stop(h)
        sys.exit(0)
    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)

    t = threading.Thread(target=sensor_loop, daemon=True)
    t.start()
    print(f"Dashboard: http://localhost:{PORT}", flush=True)
    httpd = HTTPServer(("", PORT), Handler)
    httpd.serve_forever()
