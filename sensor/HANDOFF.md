# DroneProject — Session Handoff / State of Play

_Last updated: 2026-09-14 (post realtime-sensor debugging session)_

Project root: `/Users/shivammunjal/Claude Code/DroneProject`

---

## 1. Repo layout

```
DroneProject/
├── MultiMotor/            # CURRENT 6-ch ESC firmware (LL drivers, Makefile)
│   ├── Core/Src/main.c    # 6x PWM 500Hz + soft start/stop + UART protocol
│   ├── Core/Inc/main.h    # MotorConfig table, LED/button defs
│   ├── Makefile           # CubeCLT GCC, `make flash`
│   ├── build/             # MultiMotor.{elf,bin,hex,map}
│   ├── startup_stm32c092xx.s, STM32C092RCTX_FLASH.ld
│   └── GroundStation/     # Node bridge + 6-motor dashboard (ACTIVE)
├── PWM for EMAX/          # LEGACY single-motor (TIM16 PA6) + bare_metal/ refs
├── GroundStation/         # LEGACY duplicate (hardcoded serial path)
├── Drone_can/             # DroneCAN / Hobbywing X6 Plus (Python, separate track)
└── sensor/                # SensorTile.box PRO stack (UNTRACKED in git)
```

`git status`: 7 modified firmware/doc files + untracked `sensor/`, `st_assets/`, PPT/research files.
`git log` HEAD: `1f11099 docs: add README files for firmware and dashboard`.

---

## 2. Firmware — MultiMotor (DONE, flashed, verified working)

**Board:** NUCLEO-C092RC / STM32C092RCT6 (Cortex-M0+, 48 MHz HSI, 256K flash, **30K** RAM)
**ST-LINK:** V2J48M35, SWD `4000kHz`, `mode=POWERDOWN`, NRST **not** connected.
**Build:** `cd MultiMotor && make clean && make -j8`
**Flash (ONE command, no separate -c calls):**
```bash
/opt/ST/STM32CubeCLT_1.22.0/STM32CubeProgrammer/bin/STM32_Programmer_CLI \
  -c port=SWD mode=POWERDOWN -halt -e all \
  -d build/MultiMotor.bin 0x08000000 -v -rst
```

### Motor → timer/pin map (verified vs ST examples)
| Motor | Pin | Header | Timer | AF |
|---|---|---|---|---|
| M1 | PA6 | D12 | TIM16_CH1 | AF5 |
| M2 | PA7 | D11 | TIM17_CH1 | AF5 |
| M3 | PA4 | A2  | TIM14_CH1 | AF4 |
| M4 | PA8 | D7  | TIM1_CH1  | AF2 |
| M5 | PA1 | A1  | TIM1_CH2  | AF5 |
| M6 | PA10| D2  | TIM1_CH3  | AF2 |

### PWM settings (current)
- `PSC=47` → 1 MHz tick; **`ARR=1999` → 500 Hz** (2 ms frame). 1–2 ms = 50–100% duty.
- Formerly 50 Hz (`ARR=19999`) — changed this session at user request.
- **Soft start/stop** (`main.c` lines ~18–30):
  - `#define RAMP_STEP_US 4`, `#define RAMP_INTERVAL_MS 5` → 800 µs/s slew.
  - `motor_target[6]` = commanded; `motor_ccr[6]` = actual (ramped); `ramp_update()` every 5 ms.
  - 0→20% ≈ 250 ms, 0→100% ≈ 1.25 s. Tune `RAMP_STEP_US` (↑ faster, ↓ smoother).
- Watchdog: 1000 ms silence while armed → auto-disarm (soft ramp down).
- Telemetry: `T<ccr1..ccr6>,<state>` at 10 Hz. State 0=DISARMED 1=ARMED 2=KILLED.
- UART protocol 115200 8N1: `A`=arm, `D`=disarm, `R`=recover, `S<motor>,<val>` (1-indexed), legacy `S<val>`=all.
- Button PC13 = kill switch (EXTI falling → `LL_TIM_DisableAllOutputs`, MOE off).

### ESC in use
**Hobbywing X-Rotor 40A** — official manual (HW-SM019DUL_V1) specs **50 Hz, 1100–1940 µs** and does
**not** list 500 Hz. Empirically **arms and runs fine at 500 Hz**. Watch for failure-to-arm
(repeating beeps); revert `ARR` to `19999` if needed.

### GroundStation (MultiMotor/GroundStation)
- `node server.js` → http://localhost:3000, express + ws + serialport.
- Auto-detects NUCLEO via `vendorId 0483` → `/dev/cu.usbmodem*`.
- Dashboard: 6 motor cards, master slider, keyboard `A/D/Space/Esc/Z/1-6/↑↓`.
- Keepalive every 400 ms (must stay under the 1000 ms watchdog).

---

## 3. Sensor stack — SensorTile.box PRO

**HW:** STEVAL-MKBOXPRO, STM32U585AI (M33), FW `FP-SNS-DATALOG2 3.2.0`
**USB:** `0483:5744`, enumerates as `Sensortile.box_PRO_Multi_Sensor_Streaming`
**SDK:** `sensor/external/stdatalog-pysdk` (156 MB) + `sensor/external/fp-sns-datalog2` (752 MB, CLI at
`Utilities/cli_example/bin_macos/arm64/cli_example`)
**venv:** `sensor/venv` (Python 3.14.6, stdatalog_core/pnpl 1.4.0, websockets 17.1, numpy, pandas, plotly, dash)

### Config `sensor/imu_mag_press.json`
Enabled: `lsm6dsv16x_acc` (dim3 int16, sens 0.000488, spts 1000, usb_dps 2304),
`lsm6dsv16x_gyro` (dim3 int16, sens 0.14, spts 1000, usb_dps 2304),
`lis2mdl_mag` (dim3 int16, sens 0.0015, spts 100, usb_dps 30),
`lps22df_press` (dim1 float, spts 200, usb_dps 40).
Disabled: `stts22h_temp`, `mp23db01hp_mic`, `lis2du12_acc`, `lsm6dsv16x_mlc`.
Config `sn` = `003900495130501620333154`; a box seen this session was `004B001F5130501620333154` — **SN may mismatch**.

### Scripts inventory
| File | Purpose | Status |
|---|---|---|
| `drone_dashboard.py` | **PRIMARY.** Direct USB streaming via `HSDLink` + ST `DataReader`, fuses orientation, serves HTTP `:8080` `/api/sensor` `/api/calibrate` `/api/diag`, serves `drone_3d.html` | rewritten this session |
| `drone_3d.html` | Three.js hexacopter + roll/pitch/yaw + altitude + raw cards; polls `/api/sensor` @30 Hz | works |
| `drone_server.py` | WebSocket `:8765` variant, monkey-patches `SensorAcquisitionThread` @50 Hz | alternate |
| `live_stream.py` | Terminal ANSI live display (50 Hz patch + file fallback) | works |
| `realtime.py` | Terminal ANSI, reads `.dat` files | works |
| `drone_capture.py` | Offline N-second capture → `.dat` → `.csv` | works |
| `capture_and_update.sh` | `cli_example` capture → HSD2 decode → `dashboard_data.json` → embed → open `dashboard.html` | works |
| `start_dashboard.py` | static HTTP `:8080`, CSP disabled | works |
| `index.html` | older 3D UI (expects WS `:8765`) | mismatched |
| `dashboard.html` + `dashboard_data.json` | offline Chart.js + embedded Sep-1 capture | **stale** |
| `arbitrage-demo/` | unrelated CS:GO/skin arbitrage demo | clutter |

### HSDv2 wire format (CRITICAL)
```
file/packet = [4-byte counter][usb_dps payload]
payload     = frames of [spts * dim * bytes_per_sample data][8-byte double timestamp]
```
- acc/gyro: spts=1000, dim=3, int16 → frame = 1000*3*2 + 8 = **6008 B**; usb_dps 2304
- mag: spts=100, dim=3, int16 → frame = **608 B**; usb_dps 30
- press: spts=200, dim=1, float32 → frame = **808 B**; usb_dps 40
- Older CLI `.dat` files parse correctly with this framing (verified: last sample |acc| ≈ **1.005 g** ✅).

### Fusion (in `drone_dashboard.py`)
Complementary filter, tunables:
```
ACC_LP 0.35   MAG_LP 0.10   PRESS_LP 0.20
GYRO_DB 0.40 dps   YAW_MAG_W 0.02   YAW_MAX_RATE 90 deg/s
MAG_SPIKE 0.50 G   GYRO_BIAS_N 150
```
- startup gyro-bias calibration → deadband → accel EMA → mag EMA + spike reject
- roll/pitch: complementary (gyro integrate + accel correct, α=0.97)
- yaw: **gyro-led** integrate + only 2%/update mag correction + 90°/s slew limit
  → fixed the "yaw teleports on tiny noise" bug (old code trusted mag 100%/update)
- baro EMA → altitude via `44330*(1-(P/P0)^(1/5.255))`, ground ref via `/api/calibrate`

---

## 4. Confirmed working ✅

1. Firmware 50 Hz → **500 Hz** across MultiMotor + PWM-for-EMAX + bare-metal refs + docs.
2. **Soft start/stop** ramp added, tuned for 380KV @ 24 V (large prop inertia).
3. Flashed + verified on hardware; ESC **arms and runs** at 500 Hz.
4. Sensor **right yaw smoothing**: gyro clean at `0.00` (bias+deadband), yaw stable ±1° when still.
5. Sensor **streaming live** via direct USB: `cb_counts` growing ~20/s, `cb_errors` empty.
6. **`|acc|` decode FIXED → 0.9965–1.0007 g** ✅ (was 0.58–0.78).
   Root cause: the FW **acks `set_sensor_spts` but keeps its own wire framing**.
   Fix: never push custom spts — use device defaults (acc/gyro 1000, mag 100, press 200).
7. **Board wedge FIXED** ✅ — `pkill -TERM` now runs `stop_log` cleanly (SIGTERM/SIGINT
   handlers in the **main thread** + idempotent `safe_stop`). `kill -9` still wedges; don't use it.
8. Added `/api/diag` (callback counts / errors / sample age) and `AXIS_ORDER`/`AXIS_SIGN` mounting remap.
9. **`mixer.py` + `/api/mixer`** — IMU → hexa-X mixer → 6 motor PWM (see §9).

## 5. Open problems ⚠️

| # | Problem | Notes |
|---|---|---|
| 1 | ~~`|acc|` reads 0.58–0.78 g~~ | **FIXED** — use device-default spts (§4.6) |
| 2 | ~~Native `Abort trap: 6` on `start_log`~~ | **MITIGATED** — clean SIGTERM stop. Never `kill -9`; never `stop`→`start` in one process. |
| 3 | ~~Board wedges after `kill -9`~~ | **AVOIDED** — graceful stop now works. Full power-off is still the only fix if it happens. |
| 4 | `get_component_status(0,"log_controller")` lies | returned `log_status: False` while actually logging → probe real data flow instead. |
| 5 | Press/baro nearly silent | 2–11 callbacks per 8 s (expected ~200/s). Not yet used by the mixer. |
| 6 | **Box orientation** | Currently reads `az=-0.96, roll≈179°` → mounted upside down/on its back. Set `AXIS_SIGN=(1,1,-1)` or flip the box. |
| 7 | `sensor/` untracked | never committed; no `README.md`, no `requirements.txt`. |
| 8 | Legacy `GroundStation/server.js` | hardcoded `/dev/cu.usbmodem1102`; duplicate of MultiMotor's auto-detect version. |
| 9 | No automated verification | no tests/CI; firmware validated only by manual UART + dashboard. |
| 10 | Mixer never driven on hardware | motor outputs are computed and printed but no armed bench test yet. |

## 6. Recovery cheatsheet

**SensorTile wedged** (fails to connect, `Communication Engine` error, or ABRT):
1. Kill all holders: `pkill -9 -f drone_dashboard; pkill -9 -f cli_example`
2. **Full power-cycle the box** — hold power button until all LEDs are OFF, wait 10 s, power ON.
3. Verify: `ioreg -p IOUSB | grep -i sensor`
4. Start once; **do not** call `stop_log` then `start_log` in the same process.

**NUCLEO SWD locked / bad flash:**
```bash
STM32_Programmer_CLI -c port=SWD mode=POWERDOWN -halt -e all -d fw.bin 0x08000000 -v -rst   # ONE command
```

## 7. Running things

```bash
# Sensor realtime (USB must be free; board must be freshly power-cycled)
cd "/Users/shivammunjal/Claude Code/DroneProject/sensor"
./venv/bin/python drone_dashboard.py        # → http://localhost:8080  (+ /api/sensor /api/diag)
curl -s localhost:8080/api/sensor
curl -s localhost:8080/api/diag             # cb_counts, cb_errors, sample age

# Firmware
cd "/Users/shivammunjal/Claude Code/DroneProject/MultiMotor"
make clean && make -j8 && make flash

# Motor dashboard
cd "/Users/shivammunjal/Claude Code/DroneProject/MultiMotor/GroundStation" && npm start   # :3000
```

## 8. Suggested next steps (in priority order)

1. **Confirm the `spts` fix** — start server with device-default spts and assert `|acc| ≈ 1.0 g`
   in a still test. That is the single remaining correctness bug.
2. **Make streaming crash-safe** — run USB streaming in a **subprocess** so an ABRT in the native
   lib can't kill the HTTP server; parent restarts the child and reports "sensor reconnecting".
3. **Add a still-test gate** to the fusion loop: require `|acc| ∈ [0.9, 1.1]` before trusting
   accel-derived roll/pitch (auto-detects framing desync).
4. **Commit `sensor/`** with a `README.md` + `requirements.txt`.
5. **Wire IMU → firmware**: stream `/api/sensor` roll/pitch/yaw to the NUCLEO over UART, so the
   3D model reflects real motion instead of a manual slider.
6. Optional: replace complementary filter with **Madgwick/Mahony** for better dynamic yaw.
7. Cleanup: delete/merge legacy `GroundStation/`, drop `arbitrage-demo/`.

---

## 9. Mixer — IMU → 6 motor PWM (`mixer.py` + `/api/mixer`)

### Airframe: hexa-X (6 arms every 60°, adjacent arms counter-rotate)
```
            M6        M1              M1 front-right  30°  CW
              \    /                  M2 right        90°  CCW
         M5 ---  ^  --- M2            M3 rear-right  150°  CW
              /    \                  M4 rear-left   210°  CCW
            M4        M3              M5 left        270°  CW
                                      M6 front-left  330°  CCW
             (nose up)
```
Body frame `+X = right, +Y = forward, +Z = up`. Angle = deg **clockwise from the nose**.

```
xi = sin(a)   yi = cos(a)                     # arm position
T_i = throttle + (-xi)*roll + yi*pitch + spin_i*yaw     # mix law
pwm_i = 1000 + clamp(T_i,0,1) * 1000                    # 1000-2000 us
```
Verified sign conventions (all three axes correct in `--demo`):
- `roll > 0` (roll **right**)  → boost **left** motors (M4/M5/M6), cut right (M1/M2/M3)
- `pitch > 0` (nose **up**)    → boost **front** motors (M1/M6), cut rear (M3/M4)
- `yaw > 0` (yaw **right/CW**) → boost **CCW** props (M2/M4/M6), cut CW (M1/M3/M5)
Throttle is clamped to `[0.15, 0.70]` so mix axes always have headroom (no clipping).

### Two ways to use it
```bash
# 1) HTTP — mixer-ready data + computed PWM
curl -s "localhost:8080/api/mixer?throttle=0.45&roll=0.2&pitch=-0.15&yaw=0.25"
#   -> {roll,pitch,yaw, rate:{p,q,r}, acc, mag, altitude, press,
#       mixer:{motors:[{id,pwm}...], uart:"S1,1450 ...", uart_lines:"S1,1450\n..."}}

# 2) Library / CLI
./venv/bin/python mixer.py --geometry      # print airframe table
./venv/bin/python mixer.py --demo          # mixer math, no hardware
./venv/bin/python mixer.py --watch --throttle 0.0
./venv/bin/python mixer.py --watch --serial /dev/cu.usbmodem1101 --arm   # PROPS OFF!
```
`--watch` with no `--serial` just displays; with `--serial` it writes the PWM block to the
NUCLEO and sends `D` (disarm) on exit.

### ⚠️ Firmware UART gotcha (already handled)
The firmware clears `rx_buf` on `'\n'` and **ignores the rest of a line**, so commands must be
**one per line**: `S1,1450\nS2,1450\n...`. A single space-separated line would set **only M1**.
Use `motor_command_line(pwms)` (newline-separated) for serial; `sep=" "` is display-only.
`S` commands are **ignored unless ARMED**.

### Rate PID (`RatePID` / `RateController`)
Defaults `kp=0.012, ki=0.010, kd=0.0006` (yaw `kp*1.5`, no D). Output clamped to ±0.6,
integral to ±0.25. Driven by **gyro dps**, not attitude — standard rate-mode control.
In `--watch` there is no stick, so setpoints are 0 (the craft is told to resist rotation),
scaled by `--limits` (default ±20/±20/±30 deg/s).

### Not yet done for the mixer
- Mounting orientation: box currently reads `az=-0.96 / roll≈179` → set `AXIS_SIGN=(1,1,-1)`
  (top of `drone_dashboard.py`) or physically flip the box. Mixer signs assume a correct mount.
- No arming interlock / thrust curve / idle-up in the mixer.
- No genuine bench test with props off, armed, and the motors actually spinning.
- Baro/altitude is not yet part of the mix (no altitude-hold).

---

## 10. Production-grade fusion (Mahony AHRS) — added 2026-09-14

`sensor/fusion.py` replaces the old EMA complementary filter. Driven by two
bench complaints: **lag when stopping** and **yaw moving when metal comes near**.

### Why the old filter failed
| Symptom | Cause |
|---|---|
| ~1–2 s lag on stop | 0.97 gyro weight (tau ~1.1 s), yaw pulled at only 2 %/update (tau ~1.7 s), a 90 deg/s yaw slew limit, **and a 0.40 dps gyro deadband that discarded slow rotation entirely** |
| Metal moves yaw | no field-magnitude check, no heading-innovation gate, no hard-iron calibration — a shifted field fed straight into yaw |

### What replaced it
**Mahony non-linear complementary filter on SO(3)** — the same structure as
PX4's `attitude_estimator_q` — plus **ArduPilot's magnetometer health gate**.

```
gyro   -> integrated directly, NO deadband          (zero-lag response)
accel  -> corrects roll/pitch ONLY when |a| in [0.85,1.15] g   (PX4 gate)
mag    -> corrects heading ONLY while the field is healthy:
            hard-iron calibrated
            |B| within 30 % of the reference length   (ArduPilot field_ok)
            heading innovation within 25 deg of gyro
          otherwise the filter COASTS ON GYRO: yaw drifts slowly, never jumps
bias   -> seeded from 150 static samples at startup, then trimmed only while
          nearly static (PX4: spinRate < 0.175 rad/s)
```

### Reference material actually used
- **PX4** `src/modules/attitude_estimator_q/attitude_estimator_q_main.cpp`
  + `attitude_estimator_q_params.yaml`
  `ATT_W_ACC 0.2 · ATT_W_MAG 0.1 · ATT_W_GYRO_BIAS 0.1 · ATT_BIAS_MAX 0.05`
  accel 0.9–1.1 g gate; `gainMult = min(spinRate/0.873, 10)` for mag in turns.
- **ArduPilot** `libraries/AP_Compass/AP_Compass_Backend.cpp :: field_ok()`
  (reject a sample when `|B|` deviates from the running mean).
- **Mahony et al.**, *Nonlinear Complementary Filters on the Special Orthogonal
  Group*, IEEE TAC 2008.
- ST's own MotionFX is a closed-source binary; ST's BLE library only *transports*
  quaternions, so it was not usable here.

### Two subtle bugs found while building it (both real, both fixed)
1. **Cross-product sign.** PX4 writes `corr += (k % accel_normalized)`, but its
   `k` is the earth-**down** axis in body coords (PX4 is NED). Our earth frame is
   **up**, so the product must be reversed to `cross(a_n, k)`. Using PX4's order
   with a z-up frame rotates *away* from level and drives the bias integrator
   into a runaway — measured: roll ran to **111°** on a 1 dps bias.
2. **Quaternion composition.** A re-seed must build `q = qz(yaw)·qy(pitch)·qx(roll)`.
   An earlier version used `qx·qy` and dropped yaw, so every 180°-trap recovery
   silently snapped the heading back to north.
3. **180° trap.** An attitude that is 180° out is an *unstable equilibrium*: `k`
   and `a_n` are opposed, their cross product is ~0, and the filter sits inverted
   forever. Now detected (`k·a_n < -0.5` for ~0.7 s) and re-seeded.
4. **Acquisition vs locked.** Yaw starts at an arbitrary 0°, so the innovation
   gate must be **skipped until the heading first locks** — otherwise the mag is
   rejected forever and never acquires.

### Tunables (top of `fusion.py`)
```
KP_ACC 1.00        KP_MAG 0.30        KI_BIAS 0.05
ACCEL_GATE (0.85,1.15) g             STATIC_RATE 0.175 rad/s
MAG_FIELD_TOL 0.30                   MAG_INNOV_MAX 25 deg
SPIN_REF 0.873 rad/s                 MAG_ACQUIRE_GAIN 3.0
BIAS_CAL_N 150                       FLIP_RECOVER_N 20
```
Raise `KP_ACC` for snappier levelling, lower it if the frame vibrates.

### Verify it
```bash
cd sensor && ./venv/bin/python fusion.py     # 4 self-tests
```
1. pitch tracking (err ≤ 1° in motion, ~0 at rest)
2. yaw lock to 90° (err 0.01° at rest)
3. **metal: field +140 % → yaw excursion 0.00°**, instant recovery
4. 3 g shake → accel rejected, gyro coasts

### New API / UI
- `GET /api/magcal?cmd=start|fit|cancel` — compass calibration (rotate the box
  through all orientations, then fit; saves `sensor/magcal.json`)
- `GET /api/diag` now includes a `fusion` block: `mag_used`, `mag_locked`,
  `mag_healthy`, `mag_rejects`, `mag_reason`, `gyro_bias_dps`, `calibrating`,
  `attitude_valid`
- `drone_3d.html`: **1. Start Compass Cal** / **2. Finish Compass Cal** buttons
  plus a live IMU / MAG / BIAS / CAL health panel (polls `/api/diag` at 4 Hz)

### Live result
```
roll=-0.07  pitch=+0.00  yaw=-99.10   |acc|=1.0006 g
mag_used=True  locked=True  att_valid=True
bias=[-0.125,-0.391,-0.136] dps   errors: none   age 0.01 s
yaw drift ~0.04 deg/s (was drifting/teleporting before)
```

### Still open
- Compass calibration has **not** yet been run on the real box (the flow was
  exercised and fails gracefully with <200 samples). Run it to remove the
  residual hard-iron offset.
- `magcal.json` does not exist yet — created on the first successful fit.
