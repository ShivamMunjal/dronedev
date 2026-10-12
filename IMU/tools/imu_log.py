#!/usr/bin/env python3
"""
imu_log.py - capture raw ISM330IS data from the NUCLEO-C092RC and check it.

Reads the CSV that IMU/src/main.c prints on the ST-Link VCP, logs it, and
answers the two questions you actually have when bringing an IMU up:

  1. Is it moving the right way?  -> per-axis summary + a plot, so you can see
     which axis responds when you rotate the board about a known axis.
  2. Is it scaled correctly?      -> |acc| must average ~1.000 g at rest.
     This is the check that caught a real bug in the earlier sensor project,
     where |acc| read 0.58-0.78 g.

No MEMS Studio, no ST tooling: this is just the MCU's own UART output.

Usage
-----
  python3 imu_log.py                          # find the port, log 10 s
  python3 imu_log.py -t 30 -o shake.csv       # 30 s into a file
  python3 imu_log.py --port /dev/cu.usbmodem1102
  python3 imu_log.py -t 5 --gyro-zero         # zero the gyro before logging
  python3 imu_log.py -t 10 --plot             # save a PNG (needs matplotlib)

During the capture: rotate the board slowly about one axis at a time, pausing
between, so the per-axis table and the plot are easy to read.
"""

import argparse
import glob
import math
import os
import statistics
import sys
import time

BAUD = 115200

# ---- framing -----------------------------------------------------------------
# raw    : I,<t_ms>,<gx>,<gy>,<gz>,<ax>,<ay>,<az>     counts
# scaled : S,<t_ms>,<gx>,<gy>,<gz>,<ax>,<ay>,<az>     mdps / mg
# '#' lines are comments from the firmware.

def find_port(explicit=None):
    if explicit:
        return explicit
    cands = sorted(glob.glob("/dev/cu.usbmodem*"))
    if not cands:
        sys.exit("No /dev/cu.usbmodem* found. Is the NUCLEO plugged in?")
    return cands[0]


def open_port(path):
    try:
        import serial  # pyserial
    except ImportError:
        sys.exit("pyserial missing:  pip3 install pyserial")
    return serial.Serial(path, BAUD, timeout=0.2)


def capture(port, seconds, out_path, do_zero, verbose=True):
    if do_zero:
        port.write(b"z\n")
        # The firmware averages 200 samples while holding still (~0.4 s+).
        time.sleep(2.5)

    port.reset_input_buffer()
    port.write(b"r\n")          # raw counts

    raw_rows, scl_rows = [], []
    comments = []
    t0 = time.time()
    buf = b""
    last_report = t0

    while True:
        if seconds and (time.time() - t0) >= seconds:
            break
        chunk = port.read(4096)
        if not chunk:
            continue
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip().decode("ascii", "replace")
            if not line:
                continue
            if line.startswith("#"):
                comments.append(line)
                if verbose:
                    print("  " + line)
                continue
            parts = line.split(",")
            try:
                vals = [int(x) for x in parts[1:]]
            except ValueError:
                continue
            if parts[0] == "I" and len(vals) == 7:
                raw_rows.append(vals)
            elif parts[0] == "S" and len(vals) == 7:
                scl_rows.append(vals)

        now = time.time()
        if verbose and now - last_report >= 1.0:
            n = len(raw_rows) + len(scl_rows)
            rate = n / max(1e-6, now - t0)
            acc = ""
            if raw_rows and len(raw_rows[0]) == 7:
                _, _, _, _, ax, ay, az = raw_rows[-1]
                # raw counts -> g needs the FS; report counts magnitude instead
                acc = f"  |acc|raw={math.sqrt(ax*ax+ay*ay+az*az):8.1f}"
            print(f"\r  capturing... {n:6d} samples  {rate:6.1f} Hz{acc}   ", end="")
            last_report = now

    if verbose:
        print()
    return raw_rows, scl_rows, comments


def summarise(raw_rows, scl_rows, accel_ug, gyro_mdps):
    """Print the two things that matter: scale sanity and axis behaviour."""
    print("\n=== scale check ===")
    if not raw_rows:
        print("  no raw samples captured")
        return
    ax = [r[4] for r in raw_rows]; ay = [r[5] for r in raw_rows]; az = [r[6] for r in raw_rows]
    mag = [math.sqrt(r[4]**2 + r[5]**2 + r[6]**2) for r in raw_rows]
    # counts -> g using the reported sensitivity in ug/LSB
    to_g = (accel_ug or 122) / 1e6
    mean_g = statistics.fmean(mag) * to_g
    print(f"  |acc| mean = {mean_g:.4f} g   (min {min(mag)*to_g:.4f}, max {max(mag)*to_g:.4f})")
    if 0.95 <= mean_g <= 1.05:
        print("  OK - gravity magnitude is right, so framing and scaling agree")
    else:
        print("  *** WRONG - expected ~1.000 g at rest. Check FS setting and framing.")
    print(f"  accel sensitivity used: {accel_ug} ug/LSB, gyro: {gyro_mdps} mdps/LSB")

    print("\n=== which way does it move? ===")
    print("  (rotate the board about ONE axis at a time; the column that swings")
    print("   most is the axis you are rotating about)")
    t = [r[0] for r in raw_rows]
    dt = ((t[-1] - t[0]) / 1000.0) if len(t) > 1 else 1.0
    hdrs = ["gyro X", "gyro Y", "gyro Z", "accel X", "accel Y", "accel Z"]
    units = ["counts", "counts", "counts", "counts", "counts", "counts"]
    print(f"  {'axis':<9} {'mean':>9} {'std':>9} {'min':>9} {'max':>9}   swing")
    for i, h in enumerate(hdrs):
        col = [r[1 + i] for r in raw_rows]
        std = statistics.pstdev(col) if len(col) > 1 else 0.0
        print(f"  {h:<9} {statistics.fmean(col):9.1f} {std:9.1f} "
              f"{min(col):9d} {max(col):9d}   {max(col)-min(col):9d}")
    print(f"\n  capture: {len(raw_rows)} samples over {dt:.1f} s = {len(raw_rows)/dt:.1f} Hz")

    # accel-derived tilt: a quick sanity check on the axis convention
    if raw_rows:
        roll = math.degrees(math.atan2(ay[-1], az[-1]))
        pitch = math.degrees(math.atan2(-ax[-1], math.sqrt(ay[-1]**2 + az[-1]**2)))
        print(f"  last sample tilt from accel: roll {roll:+.1f} deg, pitch {pitch:+.1f} deg")


def plot(raw_rows, png_path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n(matplotlib not installed - skipping plot.  pip3 install matplotlib)")
        return None
    if not raw_rows:
        return None
    t = [(r[0] - raw_rows[0][0]) / 1000.0 for r in raw_rows]
    fig, axs = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    for i, lbl in enumerate(["X", "Y", "Z"]):
        axs[0].plot(t, [r[1 + i] for r in raw_rows], lw=0.8, label=f"gyro {lbl}")
    axs[0].set_ylabel("gyro (counts)"); axs[0].legend(loc="upper right", ncol=3); axs[0].grid(alpha=.3)
    for i, lbl in enumerate(["X", "Y", "Z"]):
        axs[1].plot(t, [r[4 + i] for r in raw_rows], lw=0.8, label=f"accel {lbl}")
    axs[1].set_ylabel("accel (counts)"); axs[1].set_xlabel("time (s)")
    axs[1].legend(loc="upper right", ncol=3); axs[1].grid(alpha=.3)
    fig.suptitle("ISM330IS raw data (NUCLEO-C092RC, direct I2C)")
    fig.tight_layout()
    fig.savefig(png_path, dpi=110)
    return png_path


def main():
    ap = argparse.ArgumentParser(description="capture + check raw ISM330IS data")
    ap.add_argument("-p", "--port", default=None)
    ap.add_argument("-t", "--time", type=float, default=10.0,
                    help="capture seconds (0 = until Ctrl-C)")
    ap.add_argument("-o", "--out", default=None, help="CSV output path")
    ap.add_argument("--plot", action="store_true", help="also write a PNG")
    ap.add_argument("--gyro-zero", action="store_true",
                    help="send 'z' first: average the gyro while still")
    ap.add_argument("--no-zero", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    port_path = find_port(args.port)
    print(f"port : {port_path} @ {BAUD}")
    port = open_port(port_path)

    # Ask for status first - it reports WHO_AM_I, the address and the
    # sensitivities, which is everything the analysis below needs.
    port.write(b"?\n")
    time.sleep(0.4)
    banner = port.read(4096).decode("ascii", "replace")
    print(banner.strip() if banner.strip() else "(no status reply)")

    accel_ug, gyro_mdps = 122, 15259
    for line in banner.splitlines():
        if "ug/LSB" in line:
            try:
                seg = line.split("accel sens")[1]
                accel_ug = int(seg.split()[0])
                gyro_mdps = int(line.split("gyro sens")[1].split()[0])
            except Exception:
                pass

    out = args.out or (f"imu_{time.strftime('%Y%m%d_%H%M%S')}.csv")
    print(f"capture {args.time:g} s -> {out}   (move the board about one axis at a time)")

    try:
        raw, scl, _ = capture(port, args.time, out, do_zero=args.gyro_zero)
    except KeyboardInterrupt:
        raw, scl = [], []
        print("\ninterrupted")
    finally:
        port.write(b"x\n")
        port.close()

    if not raw and not scl:
        sys.exit("no samples received - check the wiring and that the firmware is flashed")

    with open(out, "w") as f:
        f.write("t_ms,gx,gy,gz,ax,ay,az\n")
        for r in (raw or scl):
            f.write(",".join(str(v) for v in r) + "\n")
    print(f"wrote {out} ({len(raw or scl)} samples)")

    summarise(raw, scl, accel_ug, gyro_mdps)

    if args.plot:
        p = plot(raw or scl, os.path.splitext(out)[0] + ".png")
        if p:
            print(f"plot  : {p}")


if __name__ == "__main__":
    main()
