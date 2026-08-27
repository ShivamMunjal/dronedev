# MultiMotor Firmware

STM32C092RCT6 firmware for 6-channel ESC PWM control at 50Hz.

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

Examples:
```
A           → ARM
S1,1500     → Motor 1 = 1500µs
S4,1800     → Motor 4 = 1800µs
D           → DISARM
```

### Telemetry (NUCLEO → Mac, 10Hz)

```
T<ccr1>,<ccr2>,<ccr3>,<ccr4>,<ccr5>,<ccr6>,<state>
```

State: 0=DISARMED, 1=ARMED, 2=KILLED

### Status Messages

| Message | Meaning |
|---|---|
| `ARMED` | Motors enabled |
| `DISARMED` | Motors disabled |
| `KILLED` | Emergency stop pressed |
| `TIMEOUT` | Watchdog fired (1s no commands) |

## Watchdog

Firmware auto-disarms if no command received for 1000ms while armed.

## Safety

- Motors always start at 1000µs (off) on ARM
- DISARM immediately stops all motors
- Button on PC13 triggers emergency stop
- Watchdog disarms on communication loss
