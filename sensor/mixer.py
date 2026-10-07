#!/usr/bin/env python3
"""
mixer.py — Hexacopter mixer: IMU attitude/rates -> 6 motor PWM outputs.

Bridges the SensorTile.box PRO (attitude + body rates) to the MultiMotor
STM32 firmware, which takes `S<motor>,<pwm>` (1-indexed, 1000-2000us).

GEOMETRY (hexa-X, 6 arms every 60 deg, viewed from above, nose = up).
Motor numbers MUST match drone_3d.html:

              M6        M5
                \\      /       M5 front-right  30 deg
           M1 ---  ^  --- M4     M4 right        90 deg
                /      \\       M3 rear-right  150 deg
              M2        M3       M2 rear-left   210 deg
                                M1 left        270 deg
               (nose up)        M6 front-left  330 deg

  angle = degrees CLOCKWISE from the nose.
  Adjacent arms spin OPPOSITE ways (3 CW / 3 CCW) so yaw torque cancels.

  Body frame: +X = right, +Y = forward (nose), +Z = up.

MIXER MATH
  Motor i sits at (xi, yi) with  xi = sin(a)  (right +),  yi = cos(a)  (fwd +).

  A thrust T_i at (xi, yi) pushing +Z produces moments
      tau_x (roll)  =  sum( yi * T_i)
      tau_y (pitch) = -sum( xi * T_i)
      tau_z (yaw)   =  sum( yawfac_i * T_i)     (prop reaction torque)

  Inverting for the standard "increase-this-to-move-this-way" convention:
      roll  > 0  -> roll RIGHT   -> boost LEFT motors  (xi < 0)  => -xi * roll
      pitch > 0  -> nose UP      -> boost FRONT motors (yi > 0)  => +yi * pitch
      yaw   > 0  -> yaw RIGHT(CW) -> boost CCW-spinning props     => +yawfac * yaw

      T_i = throttle + (-xi)*roll + yi*pitch + yawfac_i*yaw

  Mixer gain 1.0 keeps each axis at full authority when the command equals the
  full throttle band, so outputs stay in [1000, 2000] us without clipping
  (throttle is clamped to [0.15, 0.70] to leave headroom).

USAGE
  # library
  from mixer import HexaMixer
  mx = HexaMixer()
  out = mx.mix(throttle=0.45, roll=0.0, pitch=0.0, yaw=0.0)   # -> [us x6]

  # live: read IMU, run rate PID, mix, print (and optionally drive the STM32)
  ./venv/bin/python mixer.py --watch
  ./venv/bin/python mixer.py --watch --serial /dev/cu.usbmodemXXXX --arm
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.request

# ─────────────────────────────────────────────────────────────────────────────
# Airframe geometry
# ─────────────────────────────────────────────────────────────────────────────
# (name, angle_deg_from_nose_CW, spin)  spin: +1 = CCW, -1 = CW  (viewed from above)
# These angles MUST match drone_3d.html. That model places motor i at
# (x, z) = (sin(i*60-90), cos(i*60-90)) with the NOSE at -z, giving the layout
# below. Getting this wrong silently mislabels which motor is which.
HEXA_X = [
    ("M1", 270.0, -1),   # left          CW
    ("M2", 210.0, +1),   # rear-left    CCW
    ("M3", 150.0, -1),   # rear-right    CW
    ("M4",  90.0, +1),   # right        CCW
    ("M5",  30.0, -1),   # front-right   CW
    ("M6", 330.0, +1),   # front-left   CCW
]

PWM_MIN, PWM_MAX, PWM_IDLE = 1000, 2000, 1000
DEFAULT_FUSION_URL = "http://localhost:8080/api/sensor"


class HexaMixer:
    """Pure mixer: pilot/thrust commands -> 6 PWM values (us)."""

    def __init__(self, geometry=HEXA_X, pwm_min=PWM_MIN, pwm_max=PWM_MAX,
                 throttle_lo=0.15, throttle_hi=0.70, gain=1.0):
        self.pwm_min, self.pwm_max = pwm_min, pwm_max
        self.throttle_lo, self.throttle_hi = throttle_lo, throttle_hi
        self.gain = gain
        self.geometry = geometry
        # precompute per-motor coefficients
        self.coef = []
        for name, ang, spin in geometry:
            rad = math.radians(ang)
            x, y = math.sin(rad), math.cos(rad)          # right, forward
            self.coef.append({
                "name": name, "angle": ang, "spin": spin,
                "x": x, "y": y,
                "c_roll": -x,                             # roll right -> boost left
                "c_pitch": y,                             # nose up    -> boost front
                "c_yaw": float(spin),                     # yaw right  -> boost CCW
            })

    def mix(self, throttle, roll, pitch, yaw):
        """throttle 0..1 ; roll/pitch/yaw -1..+1. Returns [us] * 6 in motor order."""
        t = max(self.throttle_lo, min(self.throttle_hi, throttle))
        r = max(-1.0, min(1.0, roll)) * self.gain
        p = max(-1.0, min(1.0, pitch)) * self.gain
        y = max(-1.0, min(1.0, yaw)) * self.gain

        out = []
        for c in self.coef:
            v = t + c["c_roll"] * r + c["c_pitch"] * p + c["c_yaw"] * y
            v = max(0.0, min(1.0, v))
            out.append(round(self.pwm_min + v * (self.pwm_max - self.pwm_min)))
        return out

    def stop(self):
        return [PWM_IDLE] * len(self.geometry)

    def report(self, throttle, roll, pitch, yaw):
        """Human-readable explanation of the mix (useful for debugging on the bench)."""
        cmds = self.mix(throttle, roll, pitch, yaw)
        t = max(self.throttle_lo, min(self.throttle_hi, throttle))
        lines = [f"  throttle={t:.2f} roll={roll:+.2f} pitch={pitch:+.2f} yaw={yaw:+.2f}"]
        lines.append(f"  {'motor':<5}{'ang':>6}{'spin':>6}{'roll_c':>8}{'pit_c':>8}{'yaw_c':>8}{'pwm':>7}")
        for c, pwm in zip(self.coef, cmds):
            spin = "CCW" if c["spin"] > 0 else "CW"
            lines.append(f"  {c['name']:<5}{c['angle']:>6.0f}{spin:>6}"
                         f"{c['c_roll']:>8.2f}{c['c_pitch']:>8.2f}{c['c_yaw']:>8.2f}{pwm:>7}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Rate PID (runs on gyro dps -> corrects toward commanded rate)
# ─────────────────────────────────────────────────────────────────────────────
class RatePID:
    """One axis. Input: (setpoint_dps, measured_dps). Output: normalized correction."""

    def __init__(self, kp, ki, kd, out_limit=0.6, i_limit=0.25):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.out_limit, self.i_limit = out_limit, i_limit
        self.i = 0.0
        self.prev_meas = None
        self.prev_t = None

    def reset(self):
        self.i = 0.0
        self.prev_meas = None
        self.prev_t = None

    def update(self, setpoint, measured, now=None):
        now = time.time() if now is None else now
        dt = 0.0 if self.prev_t is None else max(1e-4, min(0.2, now - self.prev_t))
        err = setpoint - measured
        p = self.kp * err
        if dt > 0.0:
            self.i += self.ki * err * dt
            self.i = max(-self.i_limit, min(self.i_limit, self.i))
            d = 0.0 if self.prev_meas is None else self.kd * (measured - self.prev_meas) / dt
        else:
            d = 0.0
        self.prev_meas, self.prev_t = measured, now
        out = p + self.i - d
        return max(-self.out_limit, min(self.out_limit, out))


class RateController:
    """Roll/pitch/yaw rate controller -> mixer inputs."""

    def __init__(self, kp=0.012, ki=0.010, kd=0.0006):
        self.roll = RatePID(kp, ki, kd)
        self.pitch = RatePID(kp, ki, kd)
        self.yaw = RatePID(kp * 1.5, ki, 0.0)

    def reset(self):
        for a in (self.roll, self.pitch, self.yaw):
            a.reset()

    def update(self, setpoints, gyro, now=None):
        """setpoints = (roll_dps, pitch_dps, yaw_dps); gyro = (gx, gy, gz) dps."""
        now = time.time() if now is None else now
        return (
            self.roll.update(setpoints[0], gyro[0], now),
            self.pitch.update(setpoints[1], gyro[1], now),
            self.yaw.update(setpoints[2], gyro[2], now),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Sensor feed
# ─────────────────────────────────────────────────────────────────────────────
def read_sensor(url=DEFAULT_FUSION_URL, timeout=2.0):
    """Fetch fused attitude + raw IMU from the dashboard server."""
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def motor_command_line(pwms, sep="\n", trailing=True):
    """Format for the MultiMotor UART.

    The firmware parses ONE command per line (rx_buf is cleared on '\\n' and the
    remainder of a line is ignored), so each motor needs its own newline.
    Commands are 1-indexed and only accepted while ARMED.

    sep="\\n"        -> multi-line block, ready for serial.write()
    sep=" "           -> single line, for logging/display only (NOT for the STM32)
    """
    s = sep.join(f"S{i+1},{v}" for i, v in enumerate(pwms))
    return s + sep if trailing else s


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def cmd_geometry(mx):
    print("\nHexa-X geometry (nose = up, angle = deg CW from nose)")
    print(f"  {'motor':<6}{'angle':>7}{'spin':>7}{'x(right)':>10}{'y(fwd)':>9}"
          f"{'c_roll':>8}{'c_pitch':>9}{'c_yaw':>7}")
    for c in mx.coef:
        spin = "CCW" if c["spin"] > 0 else "CW"
        print(f"  {c['name']:<6}{c['angle']:>7.0f}{spin:>7}{c['x']:>10.3f}{c['y']:>9.3f}"
              f"{c['c_roll']:>8.2f}{c['c_pitch']:>9.2f}{c['c_yaw']:>7.0f}")
    print("\n  roll>0 = roll right | pitch>0 = nose up | yaw>0 = yaw right (CW)\n")


def cmd_demo(mx):
    print("\n=== MIXER DEMO (pure math, no hardware) ===")
    for label, (t, r, p, y) in [
        ("hover (neutral)",        (0.45, 0.0,  0.0,  0.0)),
        ("roll RIGHT",             (0.45, 0.3,  0.0,  0.0)),
        ("pitch nose UP",          (0.45, 0.0,  0.3,  0.0)),
        ("yaw RIGHT",              (0.45, 0.0,  0.0,  0.3)),
        ("throttle 70% (max)",     (0.70, 0.0,  0.0,  0.0)),
        ("roll+pitch+yaw, 50%",    (0.45, 0.2,  0.2,  0.2)),
    ]:
        print(f"\n{label}")
        print(mx.report(t, r, p, y))
        print("  -> UART (one cmd per line): "
              + motor_command_line(mx.mix(t, r, p, y), sep=" ").replace(" ", "  "))


def cmd_watch(mx, url, serial_port, do_arm, throttle, limits):
    rc = RateController()
    ser = None
    if serial_port:
        import serial  # pyserial
        ser = serial.Serial(serial_port, 115200, timeout=0.05)
        print(f"serial open: {serial_port}")
        if do_arm:
            ser.write(b"A\n")
            print("ARM sent (propellers must be OFF for bench tests!)")

    rl, pl, yl = limits
    print(f"\n  watching {url}   (Ctrl-C to stop)")
    print(f"  rate limits: roll±{rl} pitch±{pl} yaw±{yl} deg/s | gyro is the control input\n")
    hdr = (f"  {'roll°':>8}{'pitch°':>8}{'yaw°':>8} | "
           f"{'p':>7}{'q':>7}{'r':>7} | " + "".join(f"{'M'+str(i+1):>6}" for i in range(6)))
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    last = 0.0
    try:
        while True:
            if time.time() - last < 0.05:
                time.sleep(0.005)
                continue
            last = time.time()
            try:
                d = read_sensor(url)
            except Exception as e:
                print(f"  sensor: {e}", file=sys.stderr)
                time.sleep(0.5)
                continue

            gx, gy, gz = d.get("gyro", [0, 0, 0])
            # No pilot stick in watch mode: hold zero RATE (i.e. resist rotation)
            r_out, p_out, y_out = rc.update((0.0, 0.0, 0.0), (gx, gy, gz))
            r_out = max(-1, min(1, r_out / 0.6)) * (rl / 100.0)
            p_out = max(-1, min(1, p_out / 0.6)) * (pl / 100.0)
            y_out = max(-1, min(1, y_out / 0.6)) * (yl / 100.0)

            pwms = mx.mix(throttle, r_out, p_out, y_out)
            print(f"  {d['roll']:>8.2f}{d['pitch']:>8.2f}{d['yaw']:>8.2f} | "
                  f"{gx:>7.2f}{gy:>7.2f}{gz:>7.2f} | "
                  + "".join(f"{v:>6}" for v in pwms), end="\r")
            if ser:
                ser.write(motor_command_line(pwms).encode())
                ser.flush()
    except KeyboardInterrupt:
        print("\n  stopping")
    finally:
        if ser:
            try:
                ser.write(b"D\n")          # disarm -> firmware soft-stops
                ser.close()
                print("  DISARM sent, serial closed")
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser(description="Hexacopter mixer (IMU -> 6 motor PWM)")
    ap.add_argument("--geometry", action="store_true", help="print airframe geometry")
    ap.add_argument("--demo", action="store_true", help="run mixer math demo (no hardware)")
    ap.add_argument("--watch", action="store_true", help="live: IMU -> rate PID -> mix")
    ap.add_argument("--url", default=DEFAULT_FUSION_URL, help="fusion server JSON endpoint")
    ap.add_argument("--serial", help="STM32 serial port, e.g. /dev/cu.usbmodem1101")
    ap.add_argument("--arm", action="store_true", help="send ARM on start (PROPS OFF!)")
    ap.add_argument("--throttle", type=float, default=0.0, help="fixed throttle 0..1 in --watch")
    ap.add_argument("--limits", type=float, nargs=3, default=[20.0, 20.0, 30.0],
                    metavar=("ROLL", "PITCH", "YAW"), help="rate limits deg/s")
    args = ap.parse_args()

    mx = HexaMixer()

    if args.geometry or not any([args.demo, args.watch]):
        cmd_geometry(mx)
        if not any([args.demo, args.watch]):
            print("  Try:  --demo   (mixer math)   |   --watch   (live IMU)")
        return

    if args.demo:
        cmd_demo(mx)
    if args.watch:
        cmd_watch(mx, args.url, args.serial, args.arm, args.throttle, args.limits)


if __name__ == "__main__":
    main()
