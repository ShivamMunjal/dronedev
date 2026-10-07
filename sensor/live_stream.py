#!/usr/bin/env python3
"""SensorTile.box PRO — Real-time display (50Hz monkey-patch + file fallback)"""
import os, sys, struct, time, pathlib, signal

SDK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "external/stdatalog-pysdk")
sys.path.insert(0, SDK)
sys.path.insert(0, os.path.join(SDK, "stdatalog_core"))
sys.path.insert(0, os.path.join(SDK, "stdatalog_pnpl"))

from threading import Event, Thread
from stdatalog_core.HSD_link.HSDLink import HSDLink, SensorAcquisitionThread
from stdatalog_core.HSD.utils.type_conversion import TypeConversion

RST="\033[0m"; B="\033[1m"; DIM="\033[2m"
CY="\033[96m"; GR="\033[92m"; YL="\033[93m"; MG="\033[95m"

# Shared state from monkey-patch (50Hz for MAG/PRESS/TEMP)
live_vals = {}
live_counts = {}

# Decode metadata
decode_meta = {
    "lsm6dsv16x_acc":  {"dim":3,"sens":0.000488,"fmt":"h","sb":6},
    "lsm6dsv16x_gyro": {"dim":3,"sens":0.14,    "fmt":"h","sb":6},
    "lis2mdl_mag":     {"dim":3,"sens":0.0015,  "fmt":"h","sb":6},
    "lps22df_press":   {"dim":1,"sens":1.0,     "fmt":"f","sb":4},
    "stts22h_temp":    {"dim":1,"sens":1.0,     "fmt":"f","sb":4},
}

# Monkey-patch
def patched_run(self):
    while not self.stopped.wait(0.02):
        try:
            res = self.hsd_link.get_sensor_data(self.d_id, self.s_id, self.ss_id)
            if res is None: continue
            size, raw = res
            if not raw: continue
            live_counts[self.s_id] = live_counts.get(self.s_id, 0) + size
            if self.sensor_data_file: self.sensor_data_file.write(raw)
            m = decode_meta.get(self.s_id)
            if m:
                dim=m["dim"]; fmt=m["fmt"]; sens=m["sens"]; sb=m["sb"]
                n=len(raw)//sb
                if n>0:
                    off=(n-1)*sb
                    if fmt=='h':
                        v=struct.unpack_from("<"+"h"*dim,raw,off)
                        live_vals[self.s_id]=[round(x*sens,4)for x in v]
                    elif fmt=='f':
                        v=struct.unpack_from("<"+"f"*dim,raw,off)
                        live_vals[self.s_id]=[round(x,2)for x in v]
        except: pass

SensorAcquisitionThread.run_no_print = patched_run

META_DISP = {
    "lsm6dsv16x_acc":  {"nm":"ACCEL","u":"g",  "c":CY},
    "lsm6dsv16x_gyro": {"nm":"GYRO", "u":"dps","c":GR},
    "lis2mdl_mag":     {"nm":"MAG",  "u":"G",  "c":MG},
    "lps22df_press":   {"nm":"PRESS","u":"hPa","c":YL},
    "stts22h_temp":    {"nm":"TEMP", "u":"°C", "c":YL},
}
ORDER = ["lsm6dsv16x_acc", "lsm6dsv16x_gyro", "lis2mdl_mag", "lps22df_press", "stts22h_temp"]

def decode_from_file(dat_path, m):
    """Read file and decode last sample (fallback for ACC/GYRO)."""
    try:
        with open(dat_path, "rb") as f:
            f.seek(0, 2)
            sz = f.tell()
            if sz < m["sb"]: return None, sz
            f.seek(max(0, sz - m["sb"]*10))  # read last 10 samples
            raw = f.read()
            dim=m["dim"]; fmt=m["fmt"]; sens=m["sens"]; sb=m["sb"]
            n=len(raw)//sb
            if n==0: return None, sz
            off=(n-1)*sb
            if fmt=='h':
                v=struct.unpack_from("<"+"h"*dim,raw,off)
                return[round(x*sens,4)for x in v], sz
            else:
                v=struct.unpack_from("<"+"f"*dim,raw,off)
                return[round(x,2)for x in v], sz
    except: return None, 0

def main():
    hsd_link = HSDLink()
    hsd = hsd_link.create_hsd_link(dev_com_type="st_hsd", acquisition_folder="live_capture")
    if not hsd: print("Failed"); sys.exit(1)

    did = 0
    names = HSDLink.get_sensors_names(hsd, did, only_active=True)

    sf = []; fl = []
    for s in names:
        HSDLink.start_sensor_acquisition_thread(hsd, did, s, sf, fl, print_data_cnt=False)
    HSDLink.start_log(hsd, did, interface=1)

    time.sleep(1)
    acq = pathlib.Path("live_capture")
    dat_dir = acq
    for p in acq.rglob("*.dat"): dat_dir = p.parent; break

    running = [True]
    def h(s, f): running[0] = False
    signal.signal(signal.SIGINT, h)

    t0 = time.time()
    first = True
    file_prev = {}

    while running[0]:
        el = time.time() - t0

        # For ACC/GYRO: read from file (monkey-patch might not catch them)
        for sname in ["lsm6dsv16x_acc", "lsm6dsv16x_gyro"]:
            m = decode_meta.get(sname)
            if not m: continue
            dat = dat_dir / f"{sname}.dat"
            if not dat.exists(): continue
            val, sz = decode_from_file(dat, m)
            if val:
                live_vals[sname] = val
                live_counts[sname] = sz

        lines = []
        lines.append(f"{B}{CY}╔══════════════════════════════════════════════════════════════════╗{RST}")
        lines.append(f"{B}{CY}║{RST}  {B}SensorTile.box PRO{RST}  {CY}LIVE ●{RST}  {DIM}USB-C 0483:5744{RST}              {B}{CY}║{RST}")
        lines.append(f"{B}{CY}╚══════════════════════════════════════════════════════════════════╝{RST}")

        for sname in ORDER:
            if sname not in names: continue
            d = META_DISP.get(sname)
            val = live_vals.get(sname)
            cnt = live_counts.get(sname, 0)
            c = d["c"]

            lines.append(f"  {c}┌── {d['nm']:<6} ──────────────────────────────────────────────┐{RST}")
            if val is None:
                lines.append(f"  {c}│{RST}  {DIM}Waiting...{RST}                                                {c}│{RST}")
                lines.append(f"  {c}│{RST}                                                              {c}│{RST}")
            else:
                dim = len(val)
                if dim == 3:
                    lb = ["X","Y","Z"]
                    vstr = "   ".join(f"{c}{lb[i]}={val[i]:+.3f}{RST}" for i in range(3))
                    lines.append(f"  {c}│{RST}  {vstr}  {DIM}{d['u']}{RST}")
                    mag = sum(v**2 for v in val)**0.5
                    lines.append(f"  {c}│{RST}  {DIM}│v│={mag:.4f} {d['u']}   {cnt:,}B{RST}")
                else:
                    lines.append(f"  {c}│{RST}  {c}P = {val[0]:+.3f} {d['u']}{RST}                              {DIM}{cnt:,}B{RST}")
                    lines.append(f"  {c}│{RST}                                                              {c}│{RST}")
            lines.append(f"  {c}└──────────────────────────────────────────────────────────────┘{RST}")

        total = sum(live_counts.values())
        rate = total / el if el > 0 else 0
        lines.append(f"  {DIM}T+{el:.1f}s  │  {total/1024:.0f} KB  │  {rate/1024:.0f} KB/s  │  Ctrl+C to stop{RST}")

        while len(lines) < 25: lines.append("")

        out = ""
        if not first: out += "\033[25A"
        first = False
        for line in lines: out += f"\033[2K{line}\n"
        sys.stdout.write(out)
        sys.stdout.flush()
        time.sleep(0.1)  # 10Hz display

    sys.stdout.write("\n")
    print("Stopping...", end="", flush=True)
    for e in sf: e.set()
    HSDLink.stop_log(hsd, did)
    for f in fl:
        try: f.close()
        except: pass
    print(" ✓")

if __name__ == "__main__":
    main()
