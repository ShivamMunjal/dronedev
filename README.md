# 🚁 EMAX ESC Motor Control — Drone Project

Control an EMAX/Hobbywing ESC motor from a **web browser** via a NUCLEO-C092RC board connected over USB.

```
┌──────────────┐   WebSocket    ┌──────────────┐   USB Serial    ┌─────────────────┐   PWM    ┌───────┐
│  Browser UI  │ ◄════════════► │  Node.js     │ ◄════════════► │  NUCLEO-C092RC  │ ───────► │  ESC  │
│  (HTML/JS)   │  localhost:3000│  Server      │  115200 baud   │  STM32C092RCT6  │  PA6     │ Motor │
└──────────────┘                └──────────────┘                └─────────────────┘          └───────┘
```

---

## Hardware

| Component | Detail |
|---|---|
| **MCU** | STM32C092RCT6 (Cortex-M0+, 48MHz HSI, 256KB Flash, 30KB RAM) |
| **Board** | NUCLEO-C092RC |
| **ESC** | Hobbywing 40A 2-6S (or any standard PWM ESC) |
| **Debugger** | ST-LINK/V2-1 (on-board) |
| **USB** | USB-C cable (data, not charge-only) |

### Wiring

```
NUCLEO-C092RC                    ESC (Hobbywing 40A)
─────────────                    ───────────────────
PA6 (D12, CN6 pin 6) ────────► Signal (white/yellow)
GND  (CN6 pin 4)     ────────► GND    (black)
                                  Red (BEC 5V) → leave disconnected

ESC Power Wires:
  Thick RED   ──► LiPo + (2-6S)
  Thick BLACK ──► LiPo -
```

> ⚠️ **Never connect ESC power wires to the NUCLEO.** Power the NUCLEO via USB.

---

## Quick Start

### 1. Connect the board
Plug the NUCLEO-C092RC into your Mac via USB-C.

### 2. Start the Ground Station
```bash
cd GroundStation
./start.sh
```

### 3. Open the browser
Go to **http://localhost:3000**

### 4. Fly!
- Click **⚡ ARM** → slider unlocks, green LED on
- **Drag the throttle slider** → motor spins
- Click **🔒 DISARM** or press **Space** → motor stops
- Press **Esc** → emergency stop

---

## UART Protocol

**Serial:** 115200 baud, 8N1, on USART2 (PA2=TX, PA3=RX)

### Commands (Mac → NUCLEO)

| Command | Description |
|---|---|
| `A\n` | Arm motor (enables throttle) |
| `D\n` | Disarm motor (throttle → 0) |
| `S<value>\n` | Set throttle (1000–2000 µs pulse width) |
| `R\n` | Reset from killed state |

### Telemetry (NUCLEO → Mac)

| Message | Description |
|---|---|
| `T<ccr>,<state>\r\n` | Telemetry @10Hz. state: 0=disarmed, 1=armed, 2=killed |
| `ARMED\r\n` | Motor armed |
| `DISARMED\r\n` | Motor disarmed |
| `KILLED\r\n` | Kill switch activated |
| `TIMEOUT\r\n` | Watchdog auto-disarm (500ms no command) |

### Example Session
```
→ A\n                    # Arm
← ARMED\r\n             # Confirmation
← T1000,1\r\n           # Telemetry: 1000µs, armed
→ S1500\n               # Set 50% throttle
← T1500,1\r\n           # Telemetry: 1500µs, armed
→ D\n                    # Disarm
← DISARMED\r\n          # Confirmation
← T1000,0\r\n           # Telemetry: 1000µs, disarmed
```

---

## PWM Signal

| Parameter | Value |
|---|---|
| Timer | TIM16, Channel 1, Pin PA6 |
| Frequency | 50 Hz (20ms period) |
| Pulse range | 1000µs (min) – 2000µs (max) |
| Clock | 48MHz HSI / PSC=47 → 1MHz tick |
| ARR | 19999 (20ms) |
| CCR | 1000–2000 (1–2ms pulse) |

---

## Safety Features

| Feature | Behavior |
|---|---|
| **Arm required** | Throttle ignored unless ARMED |
| **Watchdog** | Auto-disarm after 500ms without commands |
| **GUI keepalive** | Browser sends throttle every 400ms while armed |
| **Kill switch** | Physical button (PC13) toggles kill/reset |
| **Serial disconnect** | Watchdog disarms motor automatically |
| **Killed state** | PWM output disabled (TIM16 MOE cleared) |

---

## Firmware Build & Flash

### Prerequisites
- [STM32CubeCLT](https://www.st.com/en/development-tools/stm32cubeclt.html) installed at `/opt/ST/STM32CubeCLT_1.22.0/`
- STM32CubeIDE installed (for ST-LINK programmer)

### Build
```bash
GDIR="/opt/ST/STM32CubeCLT_1.22.0/GNU-tools-for-STM32/bin"
PROJ="/path/to/PWM for EMAX"
HAL="$PROJ/Drivers/STM32C0xx_HAL_Driver"

# Compile firmware (LL drivers)
$GDIR/arm-none-eabi-gcc -mcpu=cortex-m0plus -mthumb -mfloat-abi=soft -Os \
  -DSTM32C092xx -DUSE_FULL_LL_DRIVER \
  -I"$HAL/Inc" \
  -I"$PROJ/Drivers/CMSIS/Device/ST/STM32C0xx/Include" \
  -I"$PROJ/Drivers/CMSIS/Include" \
  -c -o esc_main.o esc_firmware.c

# Compile LL driver sources
for f in ll_usart ll_gpio ll_exti ll_utils ll_rcc ll_tim; do
  $GDIR/arm-none-eabi-gcc -mcpu=cortex-m0plus -mthumb -mfloat-abi=soft -Os \
    -DSTM32C092xx -DUSE_FULL_LL_DRIVER \
    -I"$HAL/Inc" -I"$PROJ/Drivers/CMSIS/Device/ST/STM32C0xx/Include" \
    -I"$PROJ/Drivers/CMSIS/Include" \
    -c -o "st_${f}.o" "$HAL/Src/stm32c0xx_${f}.c"
done

# Compile startup + system
$GDIR/arm-none-eabi-gcc -mcpu=cortex-m0plus -mthumb -c -o startup.o startup_stm32c092rctx.s
$GDIR/arm-none-eabi-gcc -mcpu=cortex-m0plus -mthumb -Os -DSTM32C092xx \
  -I"$PROJ/Drivers/CMSIS/Device/ST/STM32C0xx/Include" -I"$PROJ/Drivers/CMSIS/Include" \
  -c -o system.o "$PROJ/Core/Src/system_stm32c0xx.c"

# Link
$GDIR/arm-none-eabi-gcc -mcpu=cortex-m0plus -mthumb -mfloat-abi=soft \
  -T STM32C092RCTX_FLASH.ld -Wl,--gc-sections \
  --specs=nano.specs --specs=nosys.specs \
  -o firmware.elf startup.o esc_main.o system.o \
  st_ll_usart.o st_ll_gpio.o st_ll_exti.o st_ll_utils.o st_ll_rcc.o st_ll_tim.o \
  -lgcc

# Generate binary
$GDIR/arm-none-eabi-objcopy -O binary firmware.elf firmware.bin
```

### Flash
```bash
CLI="/Applications/STM32CubeIDE.app/Contents/Eclipse/plugins/\
com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.macosaarch64_\
1.0.100.202603051304/tools/bin/STM32_Programmer_CLI"

# IMPORTANT: Use mode=POWERDOWN (all in ONE command)
$CLI -c port=SWD mode=POWERDOWN -halt -e all \
  -d firmware.bin 0x08000000 -v -rst
```

### Recovery (if board is bricked)
```bash
# This ALWAYS works — power-cycles the MCU via ST-LINK
$CLI -c port=SWD mode=POWERDOWN -halt -e all \
  -d firmware.bin 0x08000000 -v -rst
```

> ⚠️ All operations (erase + flash + reset) must be in **ONE CLI command**. Separate `-c` calls lose the connection.

---

## Project Structure

```
DroneProject/
├── PWM for EMAX/                  # Firmware
│   ├── bare_metal/
│   │   ├── STM32C092RCTX_FLASH.ld # Official ST linker script (30KB RAM!)
│   │   ├── startup_stm32c092rctx.s # Official ST GCC startup
│   │   └── esc_firmware.c         # ESC controller (LL drivers)
│   ├── Core/Src/                   # Original CubeMX sources
│   ├── Drivers/                    # CMSIS + HAL + LL + BSP
│   └── PWM for EMAX.ioc           # CubeMX configuration
│
├── GroundStation/                  # Web UI + Server
│   ├── start.sh                   # ← Run this!
│   ├── server.js                  # Node.js bridge (WebSocket ↔ Serial)
│   ├── package.json
│   └── public/
│       └── index.html             # Full control UI
│
└── README.md                      # This file
```

---

## Key Lessons Learned

1. **RAM is 30KB, not 32KB** — Stack pointer must be `0x20007800`. Using `0x20008000` causes crash on any `push`/`pop`.
2. **HSI divider must be set explicitly** — Call `LL_RCC_SetHSIDiv(LL_RCC_HSI_DIV_1)` or the clock may run at 24MHz.
3. **Use official ST startup + linker script** — Download from [STM32CubeC0 GitHub](https://github.com/STMicroelectronics/STM32CubeC0).
4. **Use LL drivers** — They handle register configuration correctly (especially USART baud rate calculation).
5. **Flash with `mode=POWERDOWN`** — Prevents bricking; all operations in one CLI command.
6. **Use `/dev/cu.usbmodem*`** — Not `/dev/tty.usbmodem*` on macOS.

---

## Keyboard Shortcuts (GUI)

| Key | Action |
|---|---|
| `↑` / `↓` | Throttle ±20µs |
| `A` | Arm |
| `D` / `Space` | Disarm |
| `Esc` | Emergency stop |
| `R` | Reset from killed state |
