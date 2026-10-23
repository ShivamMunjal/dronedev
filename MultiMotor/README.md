# MultiMotor Firmware

STM32C092RCT6 firmware for 6-channel ESC PWM control at 500Hz.

> **Combined build (current).** This firmware now also drives the **PMU** (I2C1)
> and the **ISM330IS IMU + ST MotionFX 6X fusion** (I2C2), so motors, battery and
> attitude all stream from one image and one serial port. Two dashboards share
> one bridge server:
> - `http://localhost:3000/`      — motors + mixer + PMU
> - `http://localhost:3000/imu.html` — IMU 3D attitude (calibrate-to-zero)
>
> Extra stream/commands added for the IMU (lowercase; uppercase stay motor/mixer):
>
> | Line / cmd | Meaning |
> |---|---|
> | `E,<t>,<roll>,<pitch>,<yaw>,<gbx>,<gby>,<gbz>` | MotionFX attitude, mdeg, ~100 Hz |
> | `IMU,ISM330IS,0x6A` | IMU detected at boot (or `IMU,NONE`) |
> | `?` | IMU/fusion status |
> | `a` / `x` | start / stop the `E` stream |
> | `z` | zero gyro bias (hold still ~1 s) |
>
> Build links `../IMU` sources + `MotionFX_CM0P_wc16_ot.a`; stack is 8 KB for
> MotionFX. Flash as usual (`make flash`, mass-erases).

## Hardware

| Motor | Pin | Header | Timer | AF |
|---|---|---|---|---|
| M1 | PA6 | D12 | TIM16_CH1 | AF5 |
| M2 | PA7 | D11 | TIM17_CH1 | AF5 |
| M3 | PA4 | A2 | TIM14_CH1 | AF4 |
| M4 | PA8 | D7 | TIM1_CH1 | AF2 |
| M5 | PA1 | A1 | TIM1_CH2 | AF5 |
| M6 | PA10 | D2 | TIM1_CH3 | AF2 |

## Requirements

- **Board:** NUCLEO-C092RC (STM32C092RCT6)
- **Toolchain:** STM32CubeCLT (arm-none-eabi-gcc)
- **Flash tool:** STM32_Programmer_CLI (comes with STM32CubeIDE)

## Build

```bash
cd MultiMotor
make clean
make -j8
```

Output: `build/MultiMotor.elf` (~5KB)

## Flash

```bash
make flash
```

Or manually:

```bash
STM32_Programmer_CLI -c port=SWD mode=POWERDOWN -halt -e all -d build/MultiMotor.bin 0x08000000 -v -rst
```

**Important:** Always use `mode=POWERDOWN` in ONE command to avoid bricking.

## UART Protocol

**Baud:** 115200, 8N1

### Commands (Mac → NUCLEO)

| Command | Description |
|---|---|
| `A\n` | ARM all motors |
| `D\n` | DISARM all motors |
| `S<motor>,<value>\n` | Set throttle (1-indexed, 1000-2000µs) |
| `K\n` | Keepalive (resets watchdog) |

### Mixer commands (new)

| Command | Description |
|---|---|
| `X<thr>,<roll>,<pitch>,<yaw>\n` | Run the mixer and apply it (**ARMED only**) |
| `Y<thr>,<roll>,<pitch>,<yaw>\n` | **Dry run**: compute and report, touch nothing (safe any time) |
| `!\n` | **EMERGENCY STOP** — force idle, disable timer outputs, zero the mixer inputs. Replies `KILLED` + `MIX,1000,0,0,0` |
| `C\n` | **Save geometry to flash** — survives reset and power-off. Replies `CFG,SAVED` or `CFG,SAVE_ERR,<rc>` |
| `Q\n` | Report mixer geometry: `Q,a1,d1,a2,d2,...a6,d6` |
| `M<motor>,<angle>,<dir>\n` | Configure one motor (1-based), angle 0-359°, dir +1/-1 |
| `P<1\|2\|3>\n` | Load preset: 1=Hexa-X, 2=Hexa+, 3=Quad-X |
| `W\n` | Verbose geometry + derived gains (bench check) |

### Power module commands (new)

| Command | Description |
|---|---|
| `B\n` | Re-probe the PMU and reply `PMU,<chip>,<addr>` + a `B,...` snapshot |
| `Z\n` | Zero the mAh / Wh counters |

Examples:
```
A                       → ARM
S1,1500                 → Motor 1 = 1500µs
Y1500,100,0,0           → dry-run mix, report only
X1500,100,0,0           → apply mix (must be armed)
M4,210,-1               → motor 4 sits at 210°, speeds up yawing right
P1                      → Hexa-X preset
B                       → battery snapshot
```

### Telemetry (NUCLEO → Mac, 10Hz)

```
T<ccr1>,<ccr2>,<ccr3>,<ccr4>,<ccr5>,<ccr6>,<state>
```

State: 0=DISARMED, 1=ARMED, 2=KILLED

### Battery telemetry (NUCLEO → Mac, 5Hz)

```
B,<mV>,<mA>,<mW>,<uAh>,<uWh>,<mC>
```

Integer base units. Example: `B,23311,31,728,3132,73000,30070` =
23.311 V, 31 mA (discharge), 728 mW, 3.132 mAh used, 73.0 mWh used,
30.070 °C die temperature.

### Status Messages

| Message | Meaning |
|---|---|
| `ARMED` | Motors enabled |
| `DISARMED` | Motors disabled |
| `KILLED` | Emergency stop pressed |
| `TIMEOUT` | Watchdog fired (1s no commands) |

## Mixer

Converts `(throttle, roll, pitch, yaw)` into the six motor commands. Geometry
is fully configurable — you tell it **where each motor sits** and which way it
reacts, so any flat layout works (hexa-X, hexa+, quad-X, Y6, custom).

### Angle and sign conventions

| Angle | Motor position |
|---|---|
| 0° | nose |
| 90° | right |
| 180° | tail |
| 270° | left |

Increasing angle is **clockwise seen from above**. Control inputs:
`roll>0` = roll right, `pitch>0` = nose up, `yaw>0` = yaw right (CW from above).

`dir` (+1/-1) says what *increasing that motor* does to yaw:
**+1 = yaws right** (that is the counter-clockwise spinning motor). If the
aircraft yaws the wrong way, flip `dir` for that motor — do not rewire.

### Default geometry (Hexa-X, preset 1)

| Motor | Pin | Angle | dir |
|---|---|---|---|
| M1 | PA6 | 30° | -1 |
| M2 | PA7 | 90° | +1 |
| M3 | PA4 | 210° | +1 |
| M4 | PA8 | 270° | -1 |
| M5 | PA1 | 150° | -1 |
| M6 | PA10 | 330° | +1 |

### Mixing maths

```
delta_i = ( roll*(-sin A_i) + pitch*(-cos A_i) + yaw*dir_i ) >> 15
out_i   = throttle + delta_i
```

Integer only (Cortex-M0+ has no FPU) with a Q15 sine table, so `sin(210°)` is
exactly `-sin(30°)`.

### Output limiting — why it does not just clamp

When the requested outputs do not fit in 1000-2000 µs the mixer:

1. **scales** the attitude deltas down (only if the spread alone is wider than
the whole range), then
2. **shifts** every output together so the *attitude differences survive* and
only the collective suffers,
3. clamps as a final safety net.

Naive per-motor clipping would instead destroy the attitude command mid-manoeuvre
and flip the aircraft. The reply shows which happened: `OK`, `SHIFTED`, `SCALED`.

Disabled motors are held at **1000 µs (idle)**, never at throttle — an unused
output with an ESC on it must not spin up.

## Power module (PMU)

Reads a Holybro PM02D (INA228/INA226, 0.5 mΩ shunt) over I2C1:

| Signal | Pin |
|---|---|
| I2C1_SCL | PB8 (CN10 pin 3) |
| I2C1_SDA | PB9 (CN10 pin 5) |
| GND | CN10 pin 9/10 |

These are free pins — the six ESC outputs use PA1/PA4/PA6/PA7/PA8/PA10.
Do **not** tie the PM's 5.2 V output to the Nucleo 5 V pin while USB is attached.

* Auto-detects INA228 @0x45 (HV) or INA226 @0x41 (LV), and auto-detects the
  I2C1 pin alternate function (AF6, falling back to AF7).
* Current is derived from `Vshunt / Rshunt`, so it is correct regardless of the
  chip's calibration register; the chip's own CURRENT register is read too and
  agrees.
* The mAh/Wh counters integrate the **microamp** value, not the rounded
  milliamp shown in telemetry, so they stay accurate at low currents.
* Low voltage is *not* acted on by the firmware — the Ground Station warns at
  3.5 V/cell and alarms at 3.3 V/cell.

## Verification tools

```bash
python3 tools/mixer_ref.py        # reference model of the mixer (pure python)
python3 tools/bench_test.py       # geometry, gains, dry-run vectors, PMU
autopilot          # (GroundStation) node test_bridge.js — WS/serial datapath
```

## Emergency stop

Triggered by the **user button (PC13)** or the **`!`** command (the dashboard's
red button). Both call the same `emergency_kill()`, so they cannot drift apart.

It does three things, in order:

1. forces every output compare to idle (1000 us),
2. **disables the timer outputs entirely** — an ESC receiving no signal is safer
   than one receiving a stale pulse,
3. **zeroes the commanded mixer inputs** — `MIX,1000,0,0,0`.

Step 3 matters: the firmware, not the GUI, owns the commanded
throttle/roll/pitch/yaw. Without it a GUI would keep its last sliders and the
next re-arm would resume from a stale, possibly high, command.

Throttle is in microseconds, so *"zero throttle" is 1000 us, not 0 us* — 0 us is
not a valid ESC pulse and the limiter would only push it back to the minimum.

Recovery is **`R`** (or pressing the button again). It always returns to
DISARMED, never straight to armed, and the mixer inputs stay zeroed. Arming with
`A` also re-zeroes them, so every arm starts from idle and centred.

While killed, `X` is rejected (`XE,NOT_ARMED`) and the GUI auto-stops its 20 Hz
command stream.

`MIX,<thr>,<roll>,<pitch>,<yaw>` is sent whenever the *firmware* changes the
command (kill, arm, disarm) and in reply to `Q`, so the dashboard sliders always
reflect reality.

## Saved geometry (flash persistence)

Motor angles/directions/enabled flags are stored in the **last 2 KB page** of
flash (`0x0803F800`), so your layout survives reset, power-off and reflash-free
reboots. The linker script reserves that page (`LENGTH = 254K` instead of
`256K`), so code can never be placed there and a save cannot corrupt firmware.

* at boot the firmware prints `CFG,LOADED` (a valid saved layout was restored)
  or `CFG,DEFAULT` (nothing stored — the Hexa-X default is used),
* any geometry change (`M`, `W`, preset `P`) is followed by `CFG,DIRTY`,
* send **`C`** (or press **💾 Save to flash** in the dashboard) to commit.

A record is 16-byte header + 56-byte payload, protected by a magic number,
version, length and FNV-1a checksum, so a blank or half-written page simply
reads as "no saved config" and falls back to the default instead of loading
garbage. Only the inputs are stored; the Q15 gains are recomputed on load, so a
future change to the gain maths cannot leave stale derived values behind.

**One mass erase (`-e all`) wipes the saved layout** — that is expected; re-save
after a full chip erase.

The Makefile uses `-MMD -MP` so **editing a header triggers a rebuild** —
without it a changed `Core/Inc/*.h` silently produced stale firmware.

`bench_test.py` and `mixer_hw_test.py` compare the firmware's actual output
against `tools/mixer_ref.py`, which uses the same integer sine table. Verified on
hardware: 8/8 dry-run vectors and 6/6 applied vectors match exactly.

## Watchdog

Firmware auto-disarms if no command received for 1000ms while armed.

## Safety

- Motors always start at 1000µs (off) on ARM
- DISARM immediately stops all motors
- Button on PC13 triggers emergency stop
- Watchdog disarms on communication loss
