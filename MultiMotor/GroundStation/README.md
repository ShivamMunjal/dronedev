# MultiMotor Ground Station

Web-based dashboard for controlling 6 ESC motors via NUCLEO-C092RC.

## Features

- 6 individual motor sliders (1000-2000µs)
- Master slider to control all motors simultaneously
- Real-time telemetry display
- ARM/DISARM controls
- Emergency stop button
- Auto-detects NUCLEO serial port
- WebSocket for live updates

## Requirements

- **Node.js:** v16 or higher
- **npm:** v7 or higher
- **Hardware:** NUCLEO-C092RC with MultiMotor firmware

## Install

```bash
cd MultiMotor/GroundStation
npm install
```

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
