#!/usr/bin/env python3
"""Independent reference model of mixer.c — used to verify firmware output.

Conventions (must match mixer.h):
  angle 0 = nose, 90 = right (clockwise from above)
  roll > 0 = roll right, pitch > 0 = nose up, yaw > 0 = yaw right
  delta_i = (roll*roll_gain + pitch*pitch_gain + yaw*yaw_gain) >> 15
  roll_gain = -sin(A), pitch_gain = -cos(A), yaw_gain = yaw_dir
"""
import math

MIN_US, MAX_US, NMOT = 1000, 2000, 6



# Same Q15 sine table as the firmware, so this validates mixer *logic* and
# not the trig rounding. Exactly symmetric: sin(a+180) = -sin(a).
SIN_Q15 = [0, 572, 1144, 1715, 2286, 2856, 3425, 3993, 4560, 5126, 5690, 6252, 6813, 7371, 7927, 8481, 9032, 9580, 10126, 10668, 11207, 11743, 12275, 12803, 13328, 13848, 14364, 14876, 15383, 15886, 16383, 16876, 17364, 17846, 18323, 18794, 19260, 19720, 20173, 20621, 21062, 21497, 21925, 22347, 22762, 23170, 23571, 23964, 24351, 24730, 25101, 25465, 25821, 26169, 26509, 26841, 27165, 27481, 27788, 28087, 28377, 28659, 28932, 29196, 29451, 29697, 29934, 30162, 30381, 30591, 30791, 30982, 31163, 31335, 31498, 31650, 31794, 31927, 32051, 32165, 32269, 32364, 32448, 32523, 32587, 32642, 32687, 32722, 32747, 32762, 32767]

def sin_q15(deg):
    deg %= 360
    if deg <= 90:
        return SIN_Q15[deg]
    if deg <= 180:
        return SIN_Q15[180 - deg]
    if deg <= 270:
        return -SIN_Q15[deg - 180]
    return -SIN_Q15[360 - deg]

def cos_q15(deg):
    return sin_q15(deg + 90)

def q15(x):
    return int(round(x * 32767))


class Mixer:
    def __init__(self, angles, yaw_dirs, enabled=None):
        self.angle = list(angles)
        self.yaw = list(yaw_dirs)
        self.en = list(enabled) if enabled else [1] * NMOT

    def gains(self, i):
        a = self.angle[i] % 360
        return (-sin_q15(a),    # roll_gain  = -sin(angle)
                -cos_q15(a),    # pitch_gain = -cos(angle)
                self.yaw[i] * 32767)

    def apply(self, thr, roll, pitch, yaw):
        delta, ds = [], []
        for i in range(NMOT):
            if not self.en[i]:
                delta.append(0)
                continue
            rg, pg, yg = self.gains(i)
            # arithmetic >> 15 == floor division for negatives
            d = (roll * rg + pitch * pg + yaw * yg) // 32768
            delta.append(d)
            ds.append(d)
        dmin, dmax = min(ds), max(ds)

        limit = "OK"
        span, avail = dmax - dmin, MAX_US - MIN_US
        if span > avail:
            scale = (avail << 15) // span
            delta = [(d * scale) // 32768 if self.en[i] else 0 for i, d in enumerate(delta)]
            ds = [d for i, d in enumerate(delta) if self.en[i]]
            dmin, dmax = min(ds), max(ds)
            limit = "SCALED"

        shift = 0
        if thr + dmax > MAX_US:
            shift = MAX_US - (thr + dmax)
        if thr + dmin + shift < MIN_US:
            shift += MIN_US - (thr + dmin + shift)
        if shift != 0 and limit == "OK":
            limit = "SHIFTED"

        out = [max(MIN_US, min(MAX_US, thr + delta[i] + shift)) if self.en[i]
               else MIN_US for i in range(NMOT)]
        return out, limit, thr + shift


HEXA_X = (30, 90, 150, 210, 270, 330)
HEXA_P = (0, 60, 120, 180, 240, 300)
YAW_ALT = (1, -1, 1, -1, 1, -1)   # alternating spin direction

if __name__ == "__main__":
    m = Mixer(HEXA_X, YAW_ALT)
    print("Hexa-X gains (angle, yaw_dir, roll_gain, pitch_gain):")
    for i in range(NMOT):
        print(f"  M{i+1}: {m.angle[i]:3d}deg dir={m.yaw[i]:+d}  "
              f"roll={m.gains(i)[0]:+6d} pitch={m.gains(i)[1]:+6d}")

    tests = [
        (1500, 0, 0, 0, "level hover"),
        (1500, 100, 0, 0, "roll right 100"),
        (1500, 0, 100, 0, "pitch nose-up 100"),
        (1500, 0, 0, 100, "yaw right 100"),
        (1500, 50, -50, 25, "mixed"),
        (1950, 100, 100, 0, "near ceiling -> should shift"),
        (1100, 100, 100, 100, "near floor -> should shift"),
        (1500, 600, 600, 600, "huge input -> should scale"),
    ]
    print("\nVerification vectors:")
    for thr, r, p, y, name in tests:
        out, lim, tu = m.apply(thr, r, p, y)
        print(f"  {name:26s} thr={thr} r={r} p={p} y={y} -> {out} {{{lim}, thr_used={tu}}}")
    print("\nExpected firmware 'Y<thr>,<roll>,<pitch>,<yaw>' output lines:")
    for thr, r, p, y, name in tests:
        out, lim, tu = m.apply(thr, r, p, y)
        print(f"  Y{thr},{r},{p},{y} -> M{','.join(str(v) for v in out)};{lim}")
