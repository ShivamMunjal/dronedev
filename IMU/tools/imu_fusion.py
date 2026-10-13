#!/usr/bin/env python3
"""
imu_fusion.py - live attitude from the NUCLEO-C092RC + ISM330IS.

Reuses the filter already validated on the SensorTile.box: `sensor/fusion.py`,
a PX4 `attitude_estimator_q` style Mahony complementary filter on SO(3). The
whole point is to run the SAME estimator on the new IMU rather than inventing a
second one, so behaviour that was tuned on the box carries over.

Differences from the box, and why they matter:

  * NO MAGNETOMETER.  The ISM330IS is a 6-axis part. Accel can observe roll and
    pitch but not heading, so yaw is pure gyro integration and WILL drift. Every
    mag path in fusion.py (hard-iron cal, field-magnitude gate, innovation gate,
    gainMult) is inert here - passing mag=None is the honest input. Do not read
    yaw as an absolute heading; it is a rate reference.

  * UNITS.  The firmware streams raw int16 counts and does no scaling, so this
    converts with the sensitivities it reports (+-4 g = 8192 LSB/g,
    +-500 dps = 15.625 mdps/LSB). If the firmware FS/ODR settings change those
    numbers change too - pass --accel-lsb-per-g / --gyro-mdps-lsb to override.

  * GYRO BIAS.  The firmware can subtract a bias captured with 'z'. The filter
    also estimates its own bias, so double-correcting hides one of them. This
    sends 'c' at startup to clear the firmware bias and lets the filter own it.

Axis convention: the chip's own axes, body z up / x forward / y right, which is
what fusion.py assumes. If your board is mounted differently, fix it here with
--remap rather than editing the shared filter.

Usage:
    python3 imu_fusion.py --port /dev/cu.usbmodem1102 --seconds 20
    python3 imu_fusion.py --port ... --csv motion.csv --plot
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "sensor"))

try:
    from fusion import MahonyAHRS
except ImportError as e:  # pragma: no cover
    sys.exit(f"cannot import sensor/fusion.py: {e}\n"
             f"(expected it next to the IMU project, at DroneProject/sensor/)")

try:
    import serial
except ImportError:  # pragma: no cover
    sys.exit("pyserial missing - use ../sensor/venv/bin/python or pip3 install pyserial")


DEFAULT_ACCEL_LSB_PER_G = 8192.0     # +-4 g
DEFAULT_GYRO_MDPS_LSB = 15.625       # +-500 dps


def remap_axes(v, spec):
    """spec is like 'x,y,z' or '-y,x,z': output axis i takes the signed input
    axis named. Lets the mounting be fixed without touching the shared filter."""
    idx = {"x": 0, "y": 1, "z": 2}
    out = []
    for tok in spec.split(","):
        sign = -1.0 if tok.startswith("-") else 1.0
        out.append(sign * v[idx[tok.lstrip("-")]])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/cu.usbmodem1102")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--accel-lsb-per-g", type=float, default=DEFAULT_ACCEL_LSB_PER_G)
    ap.add_argument("--gyro-mdps-lsb", type=float, default=DEFAULT_GYRO_MDPS_LSB)
    ap.add_argument("--remap", default=None,
                    help="e.g. 'x,y,z' (default) or '-y,x,z'")
    ap.add_argument("--csv", default=None, help="write t_ms,roll,pitch,yaw to this file")
    ap.add_argument("--replay", default=None,
                    help="process a captured log file instead of the live port "
                         "(e.g. output of: screen -L -Logfile cap.log -dmS imu <port> 115200)")
    ap.add_argument("--plot", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    a_per_lsb = 1.0 / args.accel_lsb_per_g      # g per LSB
    g_per_lsb = args.gyro_mdps_lsb / 1000.0     # dps per LSB

    def sample_lines():
        """Yield raw I, lines from the live port or a captured log."""
        if args.replay:
            with open(args.replay, "r", errors="replace") as f:
                for raw in f:
                    yield raw
            return
        ser = serial.Serial(args.port, args.baud, timeout=0.5)
        time.sleep(0.3)
        # clear any firmware-side gyro bias: the filter estimates its own
        ser.reset_input_buffer()
        ser.write(b"c\n")
        time.sleep(0.2)
        ser.reset_input_buffer()
        try:
            while True:
                line = ser.readline()
                if line:
                    yield line.decode("utf-8", "replace")
        finally:
            ser.close()

    filt = MahonyAHRS()

    rows = []
    t0 = time.time()
    last_ms = None
    n = 0

    if not args.quiet:
        print("# t_ms     roll    pitch     yaw    |a| g   gyro dps   state")
        print("# ------------------------------------------------------------------")

    try:
        for txt in sample_lines():
            txt = txt.strip()
            if not txt.startswith("I,"):
                continue
            parts = txt.split(",")
            if len(parts) != 8:
                continue
            try:
                v = [int(x) for x in parts[1:]]
            except ValueError:
                continue
            t_ms = v[0]
            graw = v[1:4]
            araw = v[4:7]

            dt = 0.01 if last_ms is None else (t_ms - last_ms) / 1000.0
            last_ms = t_ms
            if dt <= 0.0:
                continue

            gyro = [x * g_per_lsb for x in graw]      # dps
            accel = [x * a_per_lsb for x in araw]     # g
            if args.remap:
                gyro = remap_axes(gyro, args.remap)
                accel = remap_axes(accel, args.remap)

            roll, pitch, yaw = filt.update(gyro, accel, None, dt)
            n += 1
            rows.append((t_ms, roll, pitch, yaw))

            if not args.quiet and n % 10 == 0:
                an = math.sqrt(sum(x * x for x in accel))
                gn = math.sqrt(sum(x * x for x in gyro))
                state = "cal" if filt.calibrating else ("ok" if filt.attitude_valid else "seed")
                print(f"  {t_ms:8d} {roll:8.2f} {pitch:8.2f} {yaw:8.2f}"
                      f"  {an:6.3f}  {gn:8.2f}   {state}")
            if not args.replay and time.time() - t0 >= args.seconds:
                break
    except KeyboardInterrupt:
        pass

    if not rows:
        print("no samples - is the firmware streaming? (send 'r')")
        return 1

    # ---- summary: this is the part that says whether motion was tracked ----
    print(f"\n  {n} samples, {n / max(1e-9, (rows[-1][0] - rows[0][0]) / 1000.0):.1f} Hz")
    for i, name in ((1, "roll "), (2, "pitch"), (3, "yaw  ")):
        vals = [r[i] for r in rows]
        # sample-to-sample noise tells us about jitter, not about bias
        d = [abs(vals[k] - vals[k - 1]) for k in range(1, len(vals))]
        d.sort()
        print(f"  {name}: min {min(vals):8.2f}  max {max(vals):8.2f}"
              f"  median |step| {d[len(d)//2]:6.3f} deg"
              f"  p95 |step| {d[int(len(d)*0.95)]:6.3f} deg")

    if args.csv:
        with open(args.csv, "w") as f:
            f.write("t_ms,roll_deg,pitch_deg,yaw_deg\n")
            for r in rows:
                f.write(f"{r[0]},{r[1]:.4f},{r[2]:.4f},{r[3]:.4f}\n")
        print(f"  wrote {args.csv}")

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        t = [(r[0] - rows[0][0]) / 1000.0 for r in rows]
        fig, ax = plt.subplots(3, 1, sharex=True, figsize=(11, 7))
        for a, i, name in zip(ax, (1, 2, 3), ("roll", "pitch", "yaw")):
            a.plot(t, [r[i] for r in rows], lw=1.2)
            a.set_ylabel(f"{name} (deg)")
            a.grid(alpha=0.3)
        ax[2].set_xlabel("time (s)")
        ax[0].set_title("ISM330IS + Mahony (sensor/fusion.py) - accel-aided roll/pitch, gyro-only yaw")
        fig.tight_layout()
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "attitude.png")
        fig.savefig(out, dpi=110)
        print(f"  wrote {os.path.normpath(out)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
