# MultiMotor Ground Station

Web-based dashboard for controlling 6 ESC motors via NUCLEO-C092RC.

## Features

- 6 individual motor sliders (1000-2000µs)
- Master slider to control all motors simultaneously
- Real-time telemetry display
- **Battery / PMU panel** (voltage, current, power, mAh, Wh, die temp, per-cell V with low-battery warning)
- **Mixer panel** — throttle/roll/pitch/yaw sliders that drive the firmware's mixer, plus an editable motor geometry table
- **Mixer geometry editor** — set each motor's angle and yaw direction, or load a preset
- ARM/DISARM controls
- Emergency stop button
- Auto-detects NUCLEO serial port
- WebSocket for live updates

## Battery / PMU panel

Two places show battery data:

* a **summary bar** across the top (voltage, current, power, mAh, Wh, die temp,
  per-cell volts with a 4S-8S selector),
* a **Battery telemetry table** in the right panel with a labelled row per
  quantity (PMU chip + I2C address, pack voltage, current, power, charge used,
  energy used, die temp, per-cell, status).

LiPo guidance: **amber below 3.50 V/cell**, **red below 3.30 V/cell** (land now).
`die` is the INA228's own die temperature — a good sanity check that the sensor
is alive.

If the PMU is unplugged the panel shows `PMU not detected` / `PMU lost`; the
mixer and motor controls are completely unaffected. Press `Read (Q)` or send
`B` to re-probe without rebooting.

## Mixer panel

Two ways to drive the motors:

1. **Individual sliders** (existing) — sends `S<motor>,<value>`.
2. **MIX** — set THROTTLE / ROLL / PITCH / YAW and the firmware's mixer
distributes them across the six motors. While MIX is on the per-motor sliders are
read-only: they show what the mixer produced.

MIX streams `X<thr>,<roll>,<pitch>,<yaw>` at 20 Hz while armed, which also feeds
the firmware watchdog. `XE,NOT_ARMED` in the raw log means X was sent while
disarmed (the firmware refuses — arm first).

### Geometry editor (right panel)

Each row sets one motor's **angle** (0° = nose, 90° = right, clockwise seen from
above) and **yaw direction** (+1 = speeding that motor up yaws the aircraft
right). Buttons: `Hexa-X` / `Hexa+` / `Quad-X` presets, `Apply` to push the
table to the firmware, `Read (Q)` to pull the firmware's current geometry back
into the table.

> The mixer only moves motors that are **enabled**; disabled motors are held at
> idle (1000 µs). Quad-X on this 6-output board disables M5/M6.

## Pins

| Motor | Pin | Header | Timer | AF |
|---|---|---|---|---|
| M1 | PA6 | D12 | TIM16_CH1 | AF5 |
| M2 | PA7 | D11 | TIM17_CH1 | AF5 |
## Requirements

- **Node.js:** v16 or higher
- **npm:** v7 or higher
- **Hardware:** NUCLEO-C092RC with MultiMotor firmware

## Install

```bash
cd MultiMotor/GroundStation
npm install
```

> There is a second, older dashboard at `DroneProject/GroundStation` (single-ESC
> firmware). Both default to port **3000**, so run one at a time — or start this
> one alongside it with `PORT=3001 node server.js`.

## Run

```bash
node server.js
```

Then open http://localhost:3000 in your browser.

## Dashboard Layout

```
┌─────────────────────────────────────────────────────────────┐
│  🚁 MultiMotor Ground Station          WS ●  Serial ●      │
├─────────────────────────────────────────────────────────────┤
│                      [ DISARMED ]                           │
│  ⚡ ALL MOTORS  ═══════○═══════════  1000                   │
├───────────────┬───────────────┬───────────────┐             │
│   Motor 1     │   Motor 2     │   Motor 3     │             │
│  PA6/D12      │  PA7/D11      │   PA4/A2      │             │
│    1000       │    1000       │    1000       │             │
│ ──────○──── │ ──────○──── │ ──────○──── │             │
├───────────────┼───────────────┼───────────────┤             │
│   Motor 4     │   Motor 5     │   Motor 6     │             │
│  PA8/D7       │  PA10/D2      │   PA1/A1      │             │
│    1000       │    1000       │    1000       │             │
│ ──────○──── │ ──────○──── │ ──────○──── │             │
└───────────────┴───────────────┴───────────────┘             │
│        [⚡ ARM ALL]  [🔒 DISARM]  [⏬ Zero All]             │
│              [🛑 EMERGENCY STOP]                            │
└─────────────────────────────────────────────────────────────┘
```

## Controls

### Mouse
- **Individual slider** → Controls single motor
- **Master slider** → Syncs all motors to same value
- **ARM ALL** → Enables motors
- **DISARM** → Stops all motors
- **Zero All** → Sets all motors to 1000µs
- **EMERGENCY STOP** → Immediate disarm

### Keyboard

| Key | Action |
|---|---|
| `A` | ARM all motors |
| `D` or `Space` | DISARM |
| `Esc` | Emergency stop |
| `Z` | Zero all motors |
| `1-6` | Select motor |
| `↑` | Increase selected motor +20µs |
| `↓` | Decrease selected motor -20µs |

## Serial Port

Server auto-detects NUCLEO board via USB:
- Looks for STMicroelectronics vendor ID (0483)
- Prefers `/dev/cu.*` on macOS
- Retries every 3 seconds if disconnected

## Telemetry

Raw telemetry displayed in right panel:
```
T1500,1600,1700,1800,1900,2000,1
```

Format: `T<motor1>,<motor2>,...,<motor6>,<state>`

## Troubleshooting

| Issue | Fix |
|---|---|
| "No NUCLEO found" | Check USB cable, try different port |
| Motors don't respond | ARM first, then move sliders |
| Dashboard not updating | Refresh page, check WebSocket |
| Serial port busy | Close other serial monitors |
