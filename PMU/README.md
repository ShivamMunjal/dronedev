# PM02D battery telemetry — Nucleo-F401RE

Bare-metal firmware that reads a **Holybro PM02D** digital power module over I²C
and streams battery telemetry out of the ST-Link Virtual COM Port.

Verified working on the bench:

```
[I2C bus scan]
  device ACK at 0x45

[Power monitor detected]
  chip         = INA228  @ 0x45
  full scale  = 327 A
  MFG_ID       = 0x5449 (TI)
  DEVICE_ID    = 0x2281
  CONFIG wrote = 0x0000
  CAL wrote    = 0x1000  (4096)
  raw VBUS20   = 119739   raw VSHUNT20 = 49   raw CUR20 = 49   raw T = 3931
  -> monitor configured OK

# t_ms,V_V,I_A,P_W,T_C,mAh,Wh
27018,23.387,0.030,0.716,30.687,0.26,0.006
```

## 1. Wiring

| Nucleo-F401RE | PM02D 6-pin I²C cable |
|---|---|
| PB8 (I2C1_SCL) | SCL |
| PB9 (I2C1_SDA) | SDA |
| GND | GND |

* **Power the Nucleo from USB only.** Do not tie the PM's 5.2 V output to the
  Nucleo 5 V pin while USB is connected.
* Connect a **battery** to the PM02D's XT60 for meaningful readings — the bus
  voltage sense comes from the battery input, not from the I²C side.
* PB8/PB9 are open-drain with the STM32's weak internal pull-ups enabled. The
  PM02D has its own pull-ups; if your module/wiring has none, add 2.2 k–4.7 k
  to 3V3.

## 2. Build, flash, watch

```bash
./build.sh     # CMake + Ninja -> build/pmu_pm02d.{elf,hex,bin}
./flash.sh     # ST-Link SWD, no BOOT0 jumper needed
```

Watch the output (macOS — `screen` handles the VCP termios correctly, plain
`cat`/non-blocking reads do not):

```bash
screen /dev/cu.usbmodem1103 115200     # exit with Ctrl-A then K
```

Log to a file and plot it:

```bash
screen -L -dmS pmu /dev/cu.usbmodem1103 115200 && sleep 60 && screen -S pmu -X quit
# -> ./screenlog.0 is CSV
```

The firmware waits 1.5 s after boot before printing, so you have time to attach.
Press `i` at any time to re-print the banner and CSV header.

## 3. Output

```
t_ms,V_V,I_A,P_W,T_C,mAh,Wh
```

| Field | Meaning |
|---|---|
| `t_ms` | ms since boot |
| `V_V` | bus (battery) voltage, 1 mV resolution |
| `I_A` | current, positive = discharge |
| `P_W` | V × I |
| `T_C` | INA228 die temperature (`n/a` on the INA226 variant) |
| `mAh` | coulomb counter since boot (`z` key zeroes it) |
| `Wh` | energy counter since boot (`z` key zeroes it) |

Interactive keys: `i` info/header, `z` zero counters, `?` help.

## 4. Which chip is inside the PM02D?

The PM02D family uses the same 0.5 mΩ shunt with two different TI monitors:

| Variant | Chip | Address | Shunt range | Full scale |
|---|---|---|---|---|
| PM02D **LV** (6S) | INA226 | 0x41 | ±81.92 mV | 163.84 A |
| PM02D **HV** (2S–12S) | INA228 | 0x45 | ±163.84 mV | 327.68 A |

The **2S–12S "high voltage" module linked in the request is the HV variant**, so
it contains an **INA228** — this is why the HV part needs a 20-bit monitor that
can measure up to ~85 V while the INA226 tops out at 36 V.

The firmware scans the bus, identifies whichever chip is present (MFG_ID `0x5449`,
DIE `0x226`/`0x228`) and configures it accordingly, so it works with both.
`board.h` carries the electrical constants.

### Scaling (integer math, no float rounding)

* `VBUS` — INA228 LSB 195.3125 µV (`raw20 × 3125/16`); INA226 LSB 1.25 mV.
* `VSHUNT` — INA228 LSB 312.5 nV (`raw20 × 625/2`); INA226 LSB 2.5 µV.
* **Current is derived from `VSHUNT / R_SHUNT`**, not from the chip's CURRENT
  register, so it stays exact even if calibration is wrong. The CURRENT register
  is read as well and agrees (both showed raw 49 ⇒ 30.6 mA).
* `SHUNT_CAL` is still programmed for completeness: 4096 for the INA228
  (`13107.2e6 × I_lsb × R`), 2048 for the INA226 (`0.00512 / (I_lsb × R)`).

To support a module with a different shunt, change one line:

```c
#define R_SHUNT_UOHM  500u   /* src/board.h — 0.5 mOhm */
```

## 5. Project layout

```
CMakeLists.txt          cross build (no HAL, no newlib printf)
build.sh / flash.sh     convenience wrappers
linker/stm32f401re.ld   512K flash / 96K RAM, _estack, heap+stack guard
cmsis/                  vendored CMSIS device + core headers (ST/ARM, Apache-2.0)
src/startup.c           vector table, FPU enable, .data/.bss init, fault report
src/system.c            84 MHz from HSI (PLL 16/336/4), 1 ms SysTick
src/uart.c              polling USART2 + integer/fixed-point formatter
src/i2c.c               polling I2C1 master, timeouts, bus un-wedge, retries
src/ina2xx.c            INA226/INA228 driver + auto-detection
src/main.c              telemetry loop, coulomb/energy counters, commands
```

Resource use: **9.4 KB flash (1.8 %), 2.6 KB RAM (2.6 %)**.

## 6. Bring-up notes (bugs found and fixed during development)

1. **FPU was never enabled.** `main()` uses floats, so GCC emits VFP register
   saves in its prologue. With `CPACR` at its reset value this raised
   `NOCP` (`CFSR = 0x00080000`) → HardFault *before* `system_clock_init()` ran,
   which looked like "the UART does nothing". Fixed by enabling CP10/CP11 in
   `Reset_Handler`.
2. **Vector table had a NULL `SysTick_Handler` slot** → the first SysTick
   interrupt jumped to address 0. Fixed by wiring entry 15 to `SysTick_Handler`.
3. **Power and temperature unit bugs** — `P` printed mW as W (1000×) and `T`
   printed milli-°C with one decimal (10×). Both visible in the CSV and fixed.

## 7. If it does not work

| Symptom | Check |
|---|---|
| `no devices found` in the scan | SDA/SCL swapped, GND missing, no pull-ups |
| No serial output at all | use `screen`/`picocom`, not `cat`; check the port with `ls /dev/cu.usb*` |
| `!! HARD FAULT !!` on the console | a fault handler reported it — the UART is alive, so the fault is after `uart_init()` |
| Voltage reads 0.0 V | battery not connected to the PM's XT60 |
| Current reads ~0 with a load | confirm the load current actually flows *through* the module |
