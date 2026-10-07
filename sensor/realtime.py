#!/usr/bin/env python3
"""
SensorTile.box PRO — Real-time IMU + Mag + Pressure via USB-C
Uses ST's stdatalog-pysdk for USB streaming, decodes .dat files live.
"""
import os, sys, struct, time, signal, json, pathlib

SENSOR_DIR = pathlib.Path(__file__).parent
SDK_DIR = SENSOR_DIR / "external/stdatalog-pysdk"
sys.path.insert(0, str(SDK_DIR))
sys.path.insert(0, str(SDK_DIR / "stdatalog_core"))
sys.path.insert(0, str(SDK_DIR / "stdatalog_pnpl"))

from threading import Event
from stdatalog_core.HSD_link.HSDLink import HSDLink

# ── ANSI ──
N="\033[0m"; B="\033[1m"; DIM="\033[2m"
CYAN="\033[96m"; GREEN="\033[92m"; YELLOW="\033[93m"
MAGENTA="\033[95m"; RED="\033[91m"; WHITE="\033[97m"
BOLD_CYAN="\033[1;96m"; BOLD_GREEN="\033[1;92m"
BOLD_YELLOW="\033[1;93m"; BOLD_MAGENTA="\033[1;95m"

DISP = {
    "lsm6dsv16x_acc":  {"name":"ACC",  "dim":3, "dtype":"int16", "sens":0.000488, "unit":"g",   "color":BOLD_CYAN,    "ch":[CYAN,GREEN,YELLOW]},
    "lsm6dsv16x_gyro": {"name":"GYRO", "dim":3, "dtype":"int16", "sens":0.14,     "unit":"dps", "color":BOLD_GREEN,   "ch":[CYAN,GREEN,YELLOW]},
    "lis2mdl_mag":     {"name":"MAG",  "dim":3, "dtype":"int16", "sens":0.0015,   "unit":"G",   "color":BOLD_MAGENTA, "ch":[MAGENTA,RED,YELLOW]},
    "lps22df_press":   {"name":"PRESS","dim":1, "dtype":"float", "sens":1.0,      "unit":"hPa", "color":BOLD_YELLOW,  "ch":[YELLOW]},
    "lis2du12_acc":    {"name":"ACC2", "dim":3, "dtype":"int16", "sens":0.000488, "unit":"g",   "color":DIM+CYAN,     "ch":[CYAN,GREEN,YELLOW]},
    "stts22h_temp":    {"name":"TEMP", "dim":1, "dtype":"float", "sens":1.0,      "unit":"°C",  "color":DIM+YELLOW,   "ch":[YELLOW]},
}

def decode_last_sample(raw_bytes, cfg):
    dim = cfg["dim"]; dtype = cfg["dtype"]; sens = cfg["sens"]
    b_per = 2 if dtype == "int16" else 4
    sb = b_per * dim
    n = len(raw_bytes) // sb
    if n == 0:
        return None, 0
    off = (n - 1) * sb
    if dtype == "int16":
        vals = struct.unpack_from("<" + "h" * dim, raw_bytes, off)
        return [round(v * sens, 4) for v in vals], n
    else:
        vals = struct.unpack_from("<" + "f" * dim, raw_bytes, off)
        return [round(v, 2) for v in vals], n

def fmt(v, w=8):
    return f"{v:+.3f}".rjust(w)

def main():
    os.system("clear")
    print(f"{BOLD_CYAN}╔══════════════════════════════════════════════════════════════╗{N}")
    print(f"{BOLD_CYAN}║{N}  {B}SensorTile.box PRO{N} — {CYAN}Real-Time Sensor Stream{N}               {BOLD_CYAN}║{N}")
    print(f"{BOLD_CYAN}╠══════════════════════════════════════════════════════════════╣{N}")
    print(f"{BOLD_CYAN}║{N}  Board: {WHITE}STEVAL-MKBOXPRO{N}  MCU: {WHITE}STM32U585AI (M33){N}           {BOLD_CYAN}║{N}")
    print(f"{BOLD_CYAN}║{N}  USB:   {WHITE}0483:5744 WinUSB{N}  Cable: {GREEN}USB-C{N}                   {BOLD_CYAN}║{N}")
    print(f"{BOLD_CYAN}╚══════════════════════════════════════════════════════════════╝{N}")
    print()

    # Connect
    print(f"  {YELLOW}⏳ Connecting to board via USB...{N}", end="", flush=True)
    hsd_link = HSDLink()
    hsd = hsd_link.create_hsd_link(
        dev_com_type="st_hsd",
        acquisition_folder=str(SENSOR_DIR / "live_capture"),
    )
    if hsd is None:
        print(f" {RED}FAILED{N}")
        sys.exit(1)
    print(f" {GREEN}✓{N}")

    # Get sensors
    device_id = 0
    sensor_names = HSDLink.get_sensors_names(hsd, device_id, only_active=True)
    print(f"  {DIM}Active sensors: {', '.join(sensor_names)}{N}")

    # Start acquisition threads
    print(f"  {YELLOW}⏳ Starting acquisition threads...{N}", end="", flush=True)
    threads_stop_flags = []
    sensor_data_files = []
    for sname in sensor_names:
        HSDLink.start_sensor_acquisition_thread(
            hsd, device_id, sname, threads_stop_flags, sensor_data_files, print_data_cnt=False
        )
    print(f" {GREEN}✓ {len(sensor_names)} threads{N}")

    # Start FW logging
    HSDLink.start_log(hsd, device_id, interface=1)
    print(f"  {GREEN}✓ STREAMING{N}")
    print(f"  {DIM}Press Ctrl+C to stop{N}\n")

    # Get acquisition folder
    acq_folder = pathlib.Path(HSDLink.get_acquisition_folder(hsd))

    # Real-time display loop
    running = True
    def handler(sig, frame):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, handler)

    t_start = time.time()
    frame = 0
    prev_sizes = {}

    while running:
        frame += 1
        elapsed = time.time() - t_start

        lines = []
        lines.append(f"\033[2J\033[H")
        lines.append(f"{BOLD_CYAN}┌──────────────────────────────────────────────────────────────┐{N}")
        lines.append(f"{BOLD_CYAN}│{N}  {B}SensorTile.box PRO{N} — {CYAN}LIVE{N} {GREEN}●{N}  {DIM}T+{elapsed:.1f}s  Frame {frame}{N}          {BOLD_CYAN}│{N}")
        lines.append(f"{BOLD_CYAN}└──────────────────────────────────────────────────────────────┘{N}")
        lines.append("")

        for sname in sensor_names:
            cfg = DISP.get(sname)
            if cfg is None:
                continue

            dat_path = acq_folder / f"{sname}.dat"
            if not dat_path.exists():
                continue

            raw = dat_path.read_bytes()
            size = len(raw)
            delta = size - prev_sizes.get(sname, 0)
            prev_sizes[sname] = size

            val, nsamp = decode_last_sample(raw, cfg)
            if val is None:
                continue

            name = cfg["name"]; unit = cfg["unit"]
            color = cfg["color"]; ch = cfg["ch"]; dim = cfg["dim"]

            lines.append(f"  {color}┌─ {name:<6} ──────────────────────────────────────────────┐{N}")
            if dim == 3:
                labels = ["X", "Y", "Z"]
                vals_str = "  ".join(f"{ch[i]}{labels[i]}={fmt(val[i])}{N}" for i in range(3))
                lines.append(f"  {color}│{N}  {vals_str}  {DIM}{unit}{N}")
                mag = sum(v**2 for v in val) ** 0.5
                lines.append(f"  {color}│{N}  {DIM}│v│={mag:.4f} {unit}  samples={nsamp}  Δ={delta}B{N}")
            else:
                lines.append(f"  {color}│{N}  {ch[0]}P = {fmt(val[0])}{N}  {DIM}{unit}  samples={nsamp}  Δ={delta}B{N}")
            lines.append(f"  {color}└──────────────────────────────────────────────────────────┘{N}")
            lines.append("")

        # Data rate
        total_bytes = sum(prev_sizes.values())
        rate = total_bytes / elapsed if elapsed > 0 else 0
        lines.append(f"  {DIM}Total: {total_bytes/1024:.1f} KB  Rate: {rate/1024:.1f} KB/s{N}")
        lines.append(f"  {DIM}USB: 0483:5744 | FP-SNS-DATALOG2 v3.3.0 | stdatalog-pysdk | Ctrl+C to stop{N}")

        sys.stdout.write("\n".join(lines))
        sys.stdout.flush()
        time.sleep(0.5)

    # Cleanup
    print(f"\n\n  {YELLOW}⏳ Stopping...{N}", end="", flush=True)
    for ev in threads_stop_flags:
        ev.set()
    HSDLink.stop_log(hsd, device_id)
    try:
        HSDLink.save_json_device_file(hsd, device_id)
        HSDLink.save_json_acq_info_file(hsd, device_id)
    except:
        pass
    for f in sensor_data_files:
        try: f.close()
        except: pass
    print(f" {GREEN}✓{N}")
    print(f"  {DIM}Data: {acq_folder}{N}")

if __name__ == "__main__":
    main()
