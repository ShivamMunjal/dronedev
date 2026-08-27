# DroneProject

Multi-motor ESC control system for NUCLEO-C092RC (STM32C092RCT6).

## Repository Structure

```
DroneProject/
├── MultiMotor/
│   ├── Core/              # STM32 firmware source
│   │   ├── Inc/main.h
│   │   └── Src/main.c
│   ├── Drivers/           # STM32 HAL/LL drivers
│   ├── Makefile           # Build system
│   ├── README.md          # Firmware documentation
│   └── GroundStation/
│       ├── server.js      # Node.js WebSocket server
│       ├── public/        # Web dashboard
│       ├── package.json
│       └── README.md      # Dashboard documentation
├── PWM for EMAX/          # Original single-motor project
└── README.md              # This file
```

## Quick Start

### 1. Build & Flash Firmware

```bash
cd MultiMotor
make clean && make -j8
make flash
```

See [MultiMotor/README.md](MultiMotor/README.md) for details.

### 2. Run Ground Station

```bash
cd MultiMotor/GroundStation
npm install
node server.js
```

Open http://localhost:3000

See [GroundStation/README.md](MultiMotor/GroundStation/README.md) for details.

## Hardware Setup

### NUCLEO-C092RC Pin Mapping

| Motor | Pin | Header | Timer |
|---|---|---|---|
| M1 | PA6 | D12 | TIM16_CH1 |
| M2 | PA7 | D11 | TIM17_CH1 |
| M3 | PA4 | A2 | TIM14_CH1 |
| M4 | PA8 | D7 | TIM1_CH1 |
| M5 | PA1 | A1 | TIM1_CH2 |
| M6 | PA10 | D2 | TIM1_CH3 |

### Wiring

```
NUCLEO-C092RC          ESC          Motor
    D12 (PA6) ──────► Signal ──────► M1
    D11 (PA7) ──────► Signal ──────► M2
    A2  (PA4) ──────► Signal ──────► M3
    D7  (PA8) ──────► Signal ──────► M4
    A1  (PA1) ──────► Signal ──────► M5
    D2  (PA10)──────► Signal ──────► M6
    GND ─────────────► GND
    5V  ─────────────► VCC (if needed)
```

## UART Protocol

115200 baud, 8N1

| Command | Description |
|---|---|
| `A\n` | ARM |
| `D\n` | DISARM |
| `S<motor>,<value>\n` | Set throttle (1-indexed, 1000-2000µs) |

Telemetry: `T<ccr1>,...,<ccr6>,<state>` at 10Hz

## Safety

- Always test with props removed first
- Start with low throttle (1100µs) and increase slowly
- Keep emergency stop accessible
- Motors auto-disarm on 1s communication timeout

## License

MIT
