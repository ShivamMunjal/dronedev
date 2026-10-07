#!/usr/bin/env python3
"""
fusion.py — Production-grade attitude estimation for the SensorTile.box PRO.

Structure follows PX4's `attitude_estimator_q` (a Mahony non-linear
complementary filter on SO(3)), with ArduPilot-style magnetometer health
gating and hard-iron calibration.

WHY THIS REPLACES THE OLD COMPLEMENTARY FILTER
---------------------------------------------
The previous filter had two defects:

1. LAG.  roll/pitch were blended with a 0.97 gyro weight (tau ~1.1 s), yaw was
   pulled toward the mag with only 2 %/update (tau ~1.7 s), a 90 deg/s slew
   limit trailed the true yaw, and a 0.40 dps gyro deadband DISCARDED slow
   rotation entirely.  Stopping the box left the display creeping for ~2 s.

2. MAGNETIC DESTRUCTION.  Any ferrous metal near the box shifts the field, and
   that shifted heading was fed straight into yaw.  There was no field-magnitude
   check, no innovation gate, and no hard-iron calibration.

HOW THIS FIXES THEM
-------------------
* Gyro is integrated with NO deadband -> zero-lag response to real motion.
* Accel corrects roll/pitch ONLY when |a| is in [0.85, 1.15] g
  (PX4: "fuse accel data only if its norm is close to 1 g").  During fast motion
  |a| leaves that band, so the accel cannot corrupt the estimate.
* Mag corrects heading ONLY when the field looks healthy:
    - hard-iron calibrated
    - |B| within MAG_FIELD_TOL of a slow running mean   (ArduPilot field_ok)
    - heading innovation within MAG_INNOV_MAX of the gyro prediction
  When rejected, the filter COASTS ON GYRO: yaw drifts slowly but does NOT jump
  when you wave a screwdriver at it.  That is the metal-immunity you asked for.
* Gyro bias is estimated only while nearly static
  (PX4: "if spinRate < 0.175f"; 0.175 rad/s = 10 deg/s).
* Mag correction gain is scaled UP while spinning fast (PX4 `gainMult`), so yaw
  keeps up in a turn instead of lagging.

FRAMES
------
Body   : exactly what the IMU reports after the dashboard's AXIS_ORDER/AXIS_SIGN
         remap.  Flat on the desk = az ~= +1 g, so body +z is UP.
Earth  : North-East-Up, right handed (x=N, y=E, z=Up).
q      : rotation body -> earth.

Angles are extracted to match the conventions already validated on the bench:
    roll  = atan2(u.y, u.z)
    pitch = atan2(-u.x, hypot(u.y, u.z))        with u = earth-up in body
    yaw   = atan2(x_e.y, x_e.x)                 heading of body +x
                                                  (N=0, E=+90, right handed)
At rest u equals the normalised accelerometer, so roll/pitch are identical to
the old accel-derived values.

REFERENCES
----------
PX4-Autopilot  src/modules/attitude_estimator_q/attitude_estimator_q_main.cpp
               (ATT_W_ACC 0.2, ATT_W_MAG 0.1, ATT_W_GYRO_BIAS 0.1,
                ATT_BIAS_MAX 0.05 rad/s, accel 0.9-1.1 g gate, spinRate gainMult)
ArduPilot      libraries/AP_Compass/AP_Compass_Backend.cpp :: field_ok()
               (reject when the field length deviates from the running mean)
Mahony et al.  "Nonlinear Complementary Filters on the Special Orthogonal
               Group", IEEE TAC 2008.
"""

from __future__ import annotations

import json
import math
import pathlib

DEG = 180.0 / math.pi
RAD = math.pi / 180.0

# ── tunables ────────────────────────────────────────────────────────────────
KP_ACC = 1.00          # accel correction gain (1/s). tau ~= 1/KP_ACC = 1 s
KP_MAG = 0.30          # mag heading correction gain (1/s)
KI_BIAS = 0.05         # gyro-bias integral gain (PX4 ATT_W_GYRO_BIAS = 0.1)
BIAS_MAX = 0.05        # rad/s, PX4 ATT_BIAS_MAX
ACCEL_GATE = (0.85, 1.15)    # g — PX4 uses 0.9..1.1; slightly wider for cheap IMUs
STATIC_RATE = 0.175    # rad/s (10 dps) — only learn bias below this (PX4)
BIAS_CAL_N = 150       # static samples used to SEED the gyro bias at startup
SPIN_REF = 0.873       # rad/s (50 dps) — mag gain starts scaling up here (PX4)
SPIN_GAIN_MAX = 10.0   # PX4 gainMult cap

MAG_FIELD_TOL = 0.30   # reject if |B| deviates >30 % from the reference
MAG_INNOV_MAX = 25.0   # deg — reject mag if it disagrees with gyro by more
MAG_MEAN_LP = 0.02     # reference adaptation, applied ONLY while healthy
MAG_REBASELINE_N = 600  # ~20 s of continuous rejection -> treat as a real move
MAG_RECOVER = 0.15     # per-update blend used to re-acquire after rejection
MAG_ACQUIRE_GAIN = 3.0  # mag gain multiplier while acquiring the heading
MAG_RELOCK_N = 300      # sustained rejection (~10 s) -> re-acquire with gate off
FLIP_RECOVER_N = 20    # ~0.7 s of opposed accel -> re-seed (beats the 180° trap)


# ── small vector helpers ────────────────────────────────────────────────────
def q_mul(a, b):
    """Hamilton product a ⊗ b."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return [
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    ]


def q_from_euler(roll_deg, pitch_deg, yaw_deg):
    """Build the body->earth quaternion for the angle convention this module
    extracts:  q = qz(yaw) * qy(pitch) * qx(roll).

    Verified: with this order the extractor returns exactly (roll, pitch, yaw).
    Using qx*qy instead (as an earlier version did) is wrong, and dropping yaw
    entirely makes a re-seed silently snap the heading to north.
    """
    hr, hp, hy = (math.radians(roll_deg) * 0.5,
                  math.radians(pitch_deg) * 0.5,
                  math.radians(yaw_deg) * 0.5)
    qx = [math.cos(hr), math.sin(hr), 0.0, 0.0]
    qy = [math.cos(hp), 0.0, math.sin(hp), 0.0]
    qz = [math.cos(hy), 0.0, 0.0, math.sin(hy)]
    return q_normalize(q_mul(qz, q_mul(qy, qx)))


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _norm(a)
    return [a[0] / n, a[1] / n, a[2] / n] if n > 1e-12 else [0.0, 0.0, 0.0]


def _clamp(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


def wrap_pi(a):
    """Wrap an angle to [-pi, pi]."""
    while a > math.pi:
        a -= 2.0 * math.pi
    while a < -math.pi:
        a += 2.0 * math.pi
    return a


def wrap180(a):
    while a > 180.0:
        a -= 360.0
    while a < -180.0:
        a += 360.0
    return a


# ── quaternion (w, x, y, z) : body -> earth ─────────────────────────────────
def q_normalize(q):
    n = math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
    if n < 1e-12:
        return [1.0, 0.0, 0.0, 0.0]
    return [q[0] / n, q[1] / n, q[2] / n, q[3] / n]


def q_rotate(q, v):
    """Rotate a body-frame vector into the earth frame."""
    w, x, y, z = q
    vx, vy, vz = v
    # t = 2 * (q_vec x v)
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return [vx + w * tx + (y * tz - z * ty),
            vy + w * ty + (z * tx - x * tz),
            vz + w * tz + (x * ty - y * tx)]


def q_rotate_inv(q, v):
    """Rotate an earth-frame vector into the body frame (inverse rotation)."""
    return q_rotate([q[0], -q[1], -q[2], -q[3]], v)


def q_derivative(q, omega):
    """dq/dt for body rates omega (rad/s) in the body frame."""
    w, x, y, z = q
    wx, wy, wz = omega
    return [
        0.5 * (-x * wx - y * wy - z * wz),
        0.5 * (w * wx + y * wz - z * wy),
        0.5 * (w * wy - x * wz + z * wx),
        0.5 * (w * wz + x * wy - y * wx),
    ]


# ── magnetometer calibration ────────────────────────────────────────────────
class MagCalibration:
    """Hard-iron offset + soft-iron per-axis scale, fitted from min/max samples.

    Collect samples while slowly rotating the box through all orientations, then
    call fit().  The centre of the min/max box is the hard-iron offset; the
    per-axis half-ranges are equalised to make the field sphere-shaped.
    """

    def __init__(self, offset=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)):
        self.offset = list(offset)
        self.scale = list(scale)
        self._min = [1e9] * 3
        self._max = [-1e9] * 3
        self._n = 0

    def add(self, m):
        for i in range(3):
            self._min[i] = min(self._min[i], m[i])
            self._max[i] = max(self._max[i], m[i])
        self._n += 1

    @property
    def samples(self):
        return self._n

    def fit(self):
        """Returns (ok, message). Needs a decent spread on every axis."""
        if self._n < 200:
            return False, f"need more samples (have {self._n}, want >=200)"
        spans = [self._max[i] - self._min[i] for i in range(3)]
        if min(spans) < 0.05:
            return False, ("rotate the box through ALL orientations — axis span "
                           f"too small {['%.3f' % s for s in spans]}")
        self.offset = [(self._max[i] + self._min[i]) * 0.5 for i in range(3)]
        mean_r = sum(spans) / 6.0                      # mean half-range
        self.scale = [mean_r / (s * 0.5) for s in spans]
        return True, (f"offset={['%.4f' % v for v in self.offset]} "
                      f"scale={['%.3f' % v for v in self.scale]}")

    def apply(self, m):
        return [(m[i] - self.offset[i]) * self.scale[i] for i in range(3)]

    def to_dict(self):
        return {"offset": self.offset, "scale": self.scale}

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("offset", (0, 0, 0)), d.get("scale", (1, 1, 1)))

    def save(self, path):
        pathlib.Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path):
        p = pathlib.Path(path)
        if p.exists():
            try:
                return cls.from_dict(json.loads(p.read_text()))
            except Exception:
                pass
        return cls()


# ── magnetometer health monitor ─────────────────────────────────────────────
class MagHealth:
    """ArduPilot-style field-magnitude gate + a heading-innovation gate.

    `ok` is the verdict; when it goes false the mag stops steering yaw and the
    filter coasts on gyro.

    The reference magnitude is adapted ONLY while the field looks healthy.  That
    is the important detail: a disturbance must not be allowed to drag the
    reference along with it, otherwise the gate slowly "accepts" the corrupted
    field and — worse — takes many seconds to re-open once the metal is gone.
    Freezing the reference during a disturbance gives instant recovery.
    """

    def __init__(self, field_tol=MAG_FIELD_TOL, innov_max=MAG_INNOV_MAX):
        self.field_tol = field_tol
        self.innov_max = innov_max
        self.ref_len = None       # expected |B|; only adapted while healthy
        self.mean_len = None      # published running mean (diagnostics)
        self.ok = True
        self.rejects = 0
        self.reject_streak = 0
        self.last_reason = ""

    def check_field(self, m):
        """ArduPilot field_ok(): compare |B| against the reference length."""
        n = _norm(m)
        if n < 1e-6:
            self.last_reason = "zero field"
            return False
        if self.ref_len is None:
            self.ref_len = n
            self.mean_len = n
            return True
        d = abs(self.ref_len - n) / (self.ref_len + n)     # ~= relative diff
        good = d * 2.0 <= self.field_tol
        if good:
            self.ref_len = self.ref_len * (1 - MAG_MEAN_LP) + n * MAG_MEAN_LP
            self.reject_streak = 0
        else:
            self.reject_streak += 1
            # Assume a genuine environment change only after a LONG silence.
            if self.reject_streak > MAG_REBASELINE_N:
                self.ref_len = self.ref_len * 0.995 + n * 0.005
            self.last_reason = (f"field {n:.3f} vs ref {self.ref_len:.3f} "
                                f"(dev {d*200:.0f}%, tol {self.field_tol*100:.0f}%)")
        self.mean_len = self.ref_len
        return good

    def check_innovation(self, innov_deg):
        good = abs(innov_deg) <= self.innov_max
        if not good:
            self.last_reason = f"mag/gyro disagree {innov_deg:+.0f}deg"
        return good

    def update_result(self, good):
        if good:
            self.ok = True
            self.reject_streak = 0
        else:
            self.rejects += 1
            self.ok = False
        return self.ok


# ── the filter ──────────────────────────────────────────────────────────────
class MahonyAHRS:
    def __init__(self, kp_acc=KP_ACC, kp_mag=KP_MAG, ki_bias=KI_BIAS,
                 bias_max=BIAS_MAX, accel_gate=ACCEL_GATE,
                 field_tol=MAG_FIELD_TOL, innov_max=MAG_INNOV_MAX,
                 mag_cal: MagCalibration | None = None,
                 bias_cal_n=BIAS_CAL_N):
        self.kp_acc, self.kp_mag, self.ki_bias = kp_acc, kp_mag, ki_bias
        self.bias_max = bias_max
        self.accel_gate = accel_gate
        self.q = [1.0, 0.0, 0.0, 0.0]
        self.gyro_bias = [0.0, 0.0, 0.0]
        self.mag = mag_cal or MagCalibration()
        self.health = MagHealth(field_tol, innov_max)
        self.mag_decl = 0.0
        self.mag_used = False
        self.initialized = False       # seeded from the first good accel sample
        self.attitude_valid = False
        self._flip_count = 0
        self._mag_locked = False
        # Startup gyro-bias seeding.  The Mahony bias integrator alone needs
        # ~100 s to absorb a 1 dps offset (it is intentionally slow so it cannot
        # fight real motion).  Measuring the offset while the board is still
        # gives a good value immediately; the integrator then only trims it.
        self._bias_cal_n = bias_cal_n
        self._cal_acc = [0.0, 0.0, 0.0]
        self._cal_count = 0
        self.calibrating = bias_cal_n > 0

    # -- seeding ------------------------------------------------------------
    def _seed_from_accel(self, a, keep_yaw=True):
        """Set roll/pitch from an accel sample; keep the existing heading.

        The accelerometer cannot observe yaw, so a re-seed must PRESERVE it —
        otherwise every recovery would snap the compass back to zero.
        """
        u = _unit(a)
        roll = math.degrees(math.atan2(u[1], u[2]))
        pitch = math.degrees(math.atan2(-u[0], math.hypot(u[1], u[2])))
        yaw = self.angles()[2] if (keep_yaw and self.initialized) else 0.0
        self.q = q_from_euler(roll, pitch, yaw)
        self.initialized = True
        return roll, pitch

    # -- main update --------------------------------------------------------
    def update(self, gyro_dps, accel_g, mag_gauss, dt):
        """One filter step.

        gyro_dps   : [x,y,z] deg/s, body  (bias NOT pre-removed)
        accel_g    : [x,y,z] g,   body  (or None)
        mag_gauss  : [x,y,z] calibrated field, body (or None)
        dt         : seconds
        Returns (roll_deg, pitch_deg, yaw_deg).
        """
        if dt <= 0.0:
            dt = 1.0 / 30.0
        dt = min(dt, 0.2)

        gyro = [g * RAD for g in gyro_dps]

        # ── startup gyro-bias seeding (needs a still board) ────────────────
        if self.calibrating:
            if _norm(gyro) < STATIC_RATE:
                for i in range(3):
                    self._cal_acc[i] += gyro[i]
                self._cal_count += 1
                for i in range(3):
                    self.gyro_bias[i] = -self._cal_acc[i] / self._cal_count
                if self._cal_count >= self._bias_cal_n:
                    self.calibrating = False
            # keep the attitude alive while calibrating; the bias keeps improving

        if not self.initialized:
            if accel_g is not None:
                n = _norm(accel_g)
                if self.accel_gate[0] <= n <= self.accel_gate[1]:
                    self._seed_from_accel(accel_g)
            if not self.initialized:
                return self.angles()

        self.q = q_normalize(self.q)
        corr = [0.0, 0.0, 0.0]

        # ── magnetometer heading correction ────────────────────────────────
        self.mag_used = False
        if mag_gauss is not None:
            field_ok = self.health.check_field(mag_gauss)
            if field_ok:
                m_e = q_rotate(self.q, mag_gauss)
                # heading of the field in earth frame; earth x == magnetic north
                mag_err = wrap_pi(math.atan2(m_e[1], m_e[0]) - self.mag_decl)
                innov_deg = math.degrees(mag_err)

                # ACQUISITION vs LOCKED.  Yaw starts at an arbitrary 0 deg, so
                # on the first samples the mag legitimately disagrees by the
                # whole initial heading.  Applying the innovation gate then
                # would reject the mag forever and the heading would never
                # lock.  So: while unlocked, skip the gate and pull hard; once
                # the innovation is small we are locked and the gate becomes
                # the disturbance detector it is meant to be.
                if self._mag_locked:
                    ok2 = self.health.check_innovation(innov_deg)
                    gain = self.kp_mag
                else:
                    ok2 = True
                    gain = self.kp_mag * MAG_ACQUIRE_GAIN

                if self.health.update_result(ok2):
                    spin = _norm(gyro)
                    gain_mult = min(spin / SPIN_REF, SPIN_GAIN_MAX) if spin > SPIN_REF else 1.0
                    c = q_rotate_inv(self.q, [0.0, 0.0, -mag_err])
                    for i in range(3):
                        corr[i] += c[i] * gain * gain_mult
                    self.mag_used = True
                    if not self._mag_locked and abs(innov_deg) < MAG_INNOV_MAX * 0.5:
                        self._mag_locked = True
            else:
                self.health.update_result(False)
                # A long disturbance means we may have moved a long way; allow
                # re-acquisition with the gate off once the field is clean.
                if self.health.reject_streak > MAG_RELOCK_N:
                    self._mag_locked = False

        # ── accelerometer levelling correction (gated, PX4-style) ──────────
        if accel_g is not None:
            n = _norm(accel_g)
            if self.accel_gate[0] <= n <= self.accel_gate[1]:
                k = q_rotate_inv(self.q, [0.0, 0.0, 1.0])   # earth-up in body
                a_n = _unit(accel_g)

                # An attitude that is ~180 deg out is an UNSTABLE EQUILIBRIUM:
                # k and a_n are opposed, so their cross product is ~0 and the
                # filter can never walk back (it would sit inverted forever).
                # Detect the sustained disagreement and re-seed from the accel.
                if _dot(k, a_n) < -0.5:
                    self._flip_count += 1
                    if self._flip_count > FLIP_RECOVER_N:
                        self._seed_from_accel(accel_g)
                        self.gyro_bias = [0.0, 0.0, 0.0]
                        self._flip_count = 0
                        return self.angles()
                else:
                    self._flip_count = 0

                # NOTE ON SIGN: PX4 writes `corr += (k % accel_normalized)`
                # but its k is the earth-DOWN axis in body (NED).  Our earth
                # frame is Up, so our k is earth-UP and the cross product must
                # be taken the other way round.  Using PX4's order here rotates
                # AWAY from level, which drives the gyro-bias integrator into a
                # runaway (verified: roll ran to 111 deg on a 1 dps bias).
                e = _cross(a_n, k)                          # == PX4's k % accel
                for i in range(3):
                    corr[i] += e[i] * self.kp_acc
                self.attitude_valid = True
            else:
                self.attitude_valid = False

        # ── gyro bias estimation, only when nearly static (PX4) ────────────
        if _norm(gyro) < STATIC_RATE:
            for i in range(3):
                self.gyro_bias[i] += corr[i] * self.ki_bias * dt
                self.gyro_bias[i] = _clamp(self.gyro_bias[i],
                                           -self.bias_max, self.bias_max)

        # ── feed-forward gyro + integrate ──────────────────────────────────
        rates = [gyro[i] + self.gyro_bias[i] for i in range(3)]
        for i in range(3):
            corr[i] += rates[i]

        dq = q_derivative(self.q, corr)
        for i in range(4):
            self.q[i] += dq[i] * dt
        self.q = q_normalize(self.q)

        return self.angles()

    # -- outputs ------------------------------------------------------------
    def angles(self):
        """(roll, pitch, yaw) in degrees, in the dashboard's validated convention."""
        u = q_rotate_inv(self.q, [0.0, 0.0, 1.0])       # earth-up in body
        roll = math.degrees(math.atan2(u[1], u[2]))
        pitch = math.degrees(math.atan2(-u[0], math.hypot(u[1], u[2])))
        x_e = q_rotate(self.q, [1.0, 0.0, 0.0])         # body +x in earth
        yaw = math.degrees(math.atan2(x_e[1], x_e[0]))
        return roll, pitch, wrap180(yaw)

    @property
    def gyro_bias_dps(self):
        return [b * DEG for b in self.gyro_bias]

    def status(self):
        return {
            "mag_used": self.mag_used,
            "mag_healthy": self.health.ok,
            "mag_rejects": self.health.rejects,
            "mag_mean_len": round(self.health.mean_len, 4) if self.health.mean_len else None,
            "mag_reason": self.health.last_reason,
            "attitude_valid": self.attitude_valid,
            "gyro_bias_dps": [round(b, 3) for b in self.gyro_bias_dps],
            "initialized": self.initialized,
            "calibrating": self.calibrating,
            "bias_cal_samples": self._cal_count,
            "mag_locked": self._mag_locked,
        }


# ── self-test ───────────────────────────────────────────────────────────────
def _R_from_euler(roll, pitch, yaw):
    """Body->earth rotation matrix, earth = North-East-Up."""
    cr, sr = math.cos(math.radians(roll)), math.sin(math.radians(roll))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    return [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp,     cp * sr,                cp * cr],
    ]


def _apply(Rt, v):
    """Apply a rotation matrix to a vector."""
    return [sum(Rt[i][j] * v[j] for j in range(3)) for i in range(3)]


def _transpose(R):
    return [[R[j][i] for j in range(3)] for i in range(3)]


def _selftest():
    dt = 1.0 / 30.0
    # Earth field: north + down (typical northern-hemisphere dip).
    # Earth frame is N-E-U, so "down" is -z.
    M_EARTH = [0.300, 0.0, -0.440]

    print("fusion.py self-test\n")

    # ── TEST 1: pitch up 30 deg, filter must track it and keep roll at 0 ──
    print("TEST 1 — feed a true 30 deg nose-up pitch (gyro + consistent accel)")
    print(f"  {'t(s)':>5}{'true pitch':>12}{'true roll':>11}"
          f"{'est pitch':>11}{'est roll':>10}{'err°':>8}")
    f = MahonyAHRS()
    for step in range(120):
        t = step * dt
        true_pitch = 0.0 if t < 1.0 else min(30.0, (t - 1.0) * 30.0)
        R = _R_from_euler(0.0, true_pitch, 0.0)
        Rt = _transpose(R)
        a_body = _apply(Rt, [0.0, 0.0, 1.0])          # earth-up in body
        m_body = _apply(Rt, M_EARTH)
        g_body = [0.0, 30.0, 0.0] if 1.0 <= t < 2.0 else [0.0, 0.0, 0.0]
        r, p, y = f.update(g_body, a_body, m_body, dt)
        if step % 20 == 0 or step == 119:
            print(f"  {t:5.1f}{true_pitch:12.2f}{0.0:11.2f}{p:11.2f}{r:10.2f}{p-true_pitch:8.2f}")

    # ── TEST 2: yaw 90 deg, gyro-led then mag-locked ──────────────────────
    print("\nTEST 2 — true 90 deg yaw; mag should lock the heading")
    print(f"  {'t(s)':>5}{'true yaw':>10}{'est yaw':>10}{'err°':>8}{'mag':>7}")
    f2 = MahonyAHRS()
    for step in range(150):
        t = step * dt
        true_yaw = 0.0 if t < 1.0 else min(90.0, (t - 1.0) * 90.0)
        R = _R_from_euler(0.0, 0.0, true_yaw)
        Rt = _transpose(R)
        a_body = _apply(Rt, [0.0, 0.0, 1.0])
        m_body = _apply(Rt, M_EARTH)
        g_body = [0.0, 0.0, 90.0] if 1.0 <= t < 2.0 else [0.0, 0.0, 0.0]
        r, p, y = f2.update(g_body, a_body, m_body, dt)
        if step % 25 == 0 or step == 149:
            print(f"  {t:5.1f}{true_yaw:10.1f}{y:10.2f}{wrap180(y-true_yaw):8.2f}"
                  f"{'USED' if f2.mag_used else 'gated':>7}")

    # ── TEST 3: metal — field magnitude jumps 140 % ───────────────────────
    print("\nTEST 3 — METAL: field jumps +140 % at t=1 s, returns clean at t=4 s")
    print(f"  {'t(s)':>5}{'yaw':>10}{'mag':>7}{'healthy':>9}{'reason':>34}")
    f3 = MahonyAHRS()
    for step in range(240):
        t = step * dt
        R = _R_from_euler(0.0, 0.0, 0.0)
        Rt = _transpose(R)
        a_body = [0.0, 0.0, 1.0]
        scale = 2.4 if 1.0 <= t < 4.0 else 1.0
        m_body = [v * scale for v in _apply(Rt, M_EARTH)]
        r, p, y = f3.update([0.0, 0.0, 0.0], a_body, m_body, dt)
        if step % 30 == 0 or step == 239:
            print(f"  {t:5.1f}{y:10.2f}{'USED' if f3.mag_used else 'GATED':>7}"
                  f"{str(f3.health.ok):>9}{f3.health.last_reason:>34}")

    print(f"\n  yaw excursion across the whole metal event: {abs(y):.2f} deg")
    print(f"  (a naive filter let this blow through as a large yaw jump)")

    # ── TEST 4: accel gate — a hard shake must not corrupt roll/pitch ─────
    print("\nTEST 4 — 3 g shake for 1 s: accel must be REJECTED, gyro coasts")
    f4 = MahonyAHRS()
    for step in range(90):
        a = [0.0, 0.0, 3.0] if 30 <= step < 60 else [0.0, 0.0, 1.0]
        r, p, y = f4.update([0.0, 0.0, 0.0], a, [0.300, 0.0, -0.440], dt)
        if step in (29, 59, 89):
            print(f"   step {step:>3}  |a|={_norm(a):.1f}g  roll={r:7.2f}  pitch={p:7.2f}"
                  f"  accel_valid={f4.attitude_valid}")

    print(f"\n  gyro bias learned: {[round(v,3) for v in f4.gyro_bias_dps]} dps")


if __name__ == "__main__":
    _selftest()
