#!/usr/bin/env python3
"""SensorTile.box PRO — 400Hz+ Drone Data Capture
Captures IMU+MAG+PRESS at max rate to .dat files, then converts to CSV."""
import os, sys, struct, time, pathlib, json, csv

SDK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "external/stdatalog-pysdk")
sys.path.insert(0, SDK)
sys.path.insert(0, os.path.join(SDK, "stdatalog_core"))
sys.path.insert(0, os.path.join(SDK, "stdatalog_pnpl"))

from stdatalog_core.HSD_link.HSDLink import HSDLink

def main():
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    print(f"╔══════════════════════════════════════════════════════════╗")
    print(f"║  SensorTile.box PRO — Drone Capture ({duration}s)              ║")
    print(f"║  IMU: 1920Hz │ MAG: 100Hz │ PRESS: 200Hz                ║")
    print(f"╚══════════════════════════════════════════════════════════╝")
    print()

    # Connect
    print("Connecting...", end="", flush=True)
    hsd_link = HSDLink()
    hsd = hsd_link.create_hsd_link(dev_com_type="st_hsd", acquisition_folder="drone_data")
    if not hsd:
        print(" FAILED"); sys.exit(1)
    print(" ✓")

    did = 0
    names = HSDLink.get_sensors_names(hsd, did, only_active=True)
    print(f"Sensors: {', '.join(names)}")

    # Start capture
    sf = []; fl = []
    for s in names:
        HSDLink.start_sensor_acquisition_thread(hsd, did, s, sf, fl, print_data_cnt=False)
    HSDLink.start_log(hsd, did, interface=1)

    print(f"Recording {duration}s... ", end="", flush=True)
    time.sleep(duration)

    # Stop
    for e in sf: e.set()
    HSDLink.stop_log(hsd, did)
    HSDLink.save_json_device_file(hsd, did)
    HSDLink.save_json_acq_info_file(hsd, did)
    for f in fl:
        try: f.close()
        except: pass
    print("✓")

    # Find captured data
    acq = pathlib.Path("drone_data")
    dat_dir = acq
    for p in acq.rglob("*.dat"):
        dat_dir = p.parent; break

    # Load device config for decode params
    cfg_path = dat_dir / "device_config.json"
    if not cfg_path.exists():
        print("No device_config.json found"); return

    cfg = json.loads(cfg_path.read_text())
    sensor_params = {}
    for dev in cfg.get("devices", []):
        for comp in dev.get("components", []):
            for k, v in comp.items():
                if isinstance(v, dict) and "data_type" in v:
                    sensor_params[k] = v

    # Decode and convert to CSV
    print(f"\nDecoding and converting to CSV...")
    for sname in names:
        dat_path = dat_dir / f"{sname}.dat"
        if not dat_path.exists():
            continue

        params = sensor_params.get(sname, {})
        dim = params.get("dim", 1)
        dtype = params.get("data_type", "int16")
        sens = params.get("sensitivity", 1.0)
        bp = 2 if dtype == "int16" else 4
        sb = bp * dim

        raw = dat_path.read_bytes()
        n = len(raw) // sb

        if n == 0:
            print(f"  {sname}: no data")
            continue

        # Decode all samples
        samples = []
        for i in range(n):
            off = i * sb
            if dtype == "int16":
                vals = struct.unpack_from("<" + "h" * dim, raw, off)
                samples.append([round(v * sens, 4) for v in vals])
            else:
                vals = struct.unpack_from("<" + "f" * dim, raw, off)
                samples.append([round(v, 4) for v in vals])

        # Write CSV
        csv_path = dat_dir / f"{sname}.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            if dim == 3:
                writer.writerow(["sample", "x", "y", "z"])
            else:
                writer.writerow(["sample", "value"])
            for i, s in enumerate(samples):
                writer.writerow([i] + s)

        odr = params.get("measodr", params.get("odr", "?"))
        print(f"  {sname}: {n:,} samples → {csv_path.name} ({odr} Hz)")

    print(f"\nData saved in: {dat_dir}/")
    print(f"Files:")
    for f in sorted(dat_dir.iterdir()):
        print(f"  {f.name} ({f.stat().st_size:,} bytes)")

if __name__ == "__main__":
    main()
