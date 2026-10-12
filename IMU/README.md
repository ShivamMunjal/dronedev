# IMU — raw ISM330IS data on the NUCLEO-C092RC

Reads an **ISM330IS** 6-axis IMU (on an **STEVAL-MKI230KA** DIL24 adapter) over
I²C1 and streams **raw inertial data** as CSV on the ST-Link VCP. No MEMS Studio,
no ST tooling, no closed protocol — just the MCU reading registers.

## Why take the adapter off the MKI109V3

The adapter arrived plugged into a **STEVAL-MKI109V3** motherboard. That board
cannot be scripted from the Mac:

| Probe of the MKI109V3 (firmware `ProfiF4_MKI109V3`) | Result |
|---|---|
| Its own command words (`START`, `GET_PRESENCE`, … found as strings in the .bin) | no reply |
| 115200 / 921600 / 1843200 baud, with and without DTR | no reply |
| ST `stdatalog` ASPEP handshake | `ASPEPHeaderError` |
| ST-Link / datalog firmware to replace it with | none shipped for this board |

It only answers ST's closed binary protocol, i.e. MEMS Studio. So the shortest
path to raw data is to **take the DIL24 adapter out of that socket and wire it
here** — which is where the sensor has to end up anyway for closed-loop control.

## Wiring

The IMU uses **I2C2**. The PMU owns **I2C1** on the Arduino header
(**D14 = PB9 = I2C1_SDA**, **D15 = PB8 = I2C1_SCL** - UM3353 Table 12), and
I2C2 is a separate peripheral, so the two never share a bus and the IMU never
waits on the PMU's polling.

Two presets in `src/board.h`, selected with one `#define`:

| Preset | SCL | SDA | Where |
|---|---|---|---|
| `IMU_I2C_CFG_ARDUINO` *(default)* | **D8** = PA9, AF8 | **D5** = PB4, AF14 | Arduino header (CN5 pin 1 / CN9 pin 6) |
| `IMU_I2C_CFG_MORPHO` | **PB10**, AF14 | **PB11**, AF14 | ST morpho (CN10 pin 34 / CN7 pin 37) |

```
sensor board (MKI230A J1 / MKIGIBV5 DIL24)      NUCLEO-C092RC
  SCL / SPC   -->  D8  (PA9,  I2C2_SCL)   [or PB10 on CN10 pin 34]
  SDA / SDI   <->  D5  (PB4,  I2C2_SDA)   [or PB11 on CN7  pin 37]
  VDD, VDDIO  -->  3V3
  GND         -->  GND
  CS          -->  3V3    (low selects SPI; then I2C is silent)
  SA0/SDO     -->  GND = 0x6A, 3V3 = 0x6B
  D14/D15 (PB9/PB8, I2C1) -- left alone, used by the PM02D
```

Both presets are free of the 6 motor pins, the LEDs, the button, USART2 and
SWD. Verified against the datasheet AF tables (AF number confirmed by column
alignment, not eyeballed) and UM3353 for the connector positions:

```
PA9  = I2C2_SCL @ AF8     PB4  = I2C2_SDA @ AF14
PB10 = I2C2_SCL @ AF14    PB11 = I2C2_SDA @ AF14
PB13 = I2C2_SCL @ AF14    PB14 = I2C2_SDA @ AF14
PA11 = I2C2_SCL @ AF6     PA12 = I2C2_SDA @ AF6
PA6  = I2C2_SDA @ AF6     PA7  = I2C2_SCL @ AF6   (PA6/PA7 = motors M1/M2)
```

Note that **no I2C2 pair on the Arduino header shares a single AF** (PA9 is AF8
while PB4 is AF14), which is why `i2c_init_on_pins2()` takes an independent AF
per pin. `PA9/PA10` is the aligned pair but **PA10 is motor M6**, and PB3 is
SWO/JTDO, so neither is used here.

To move the IMU to different pins or back to I2C1, edit the four `IMU_I2C_*`
defines in `src/board.h` - the driver takes the instance, port letters, pins
and AF from there. If the AF is unknown, `i2c_init_on_pins()` accepts any AF and
the `p` probe command sweeps 0..15 to find it.

The PM02D power module can share this bus — INA228 `0x45` / INA226 `0x41` do not
collide with the ISM330IS at `0x6A`/`0x6B`. **Both addresses are probed**, so you
do not have to know how SA0 is tied.

## Build and flash

```bash
cd IMU
./build.sh          # CMake + arm-none-eabi-gcc  -> build/imu_ism330is_c092rc.{elf,bin,hex}
./flash.sh          # STM32_Programmer_CLI, SWD
```

9.1 KB flash / 2.6 KB RAM.

## Capture on the Mac

```bash
# pyserial is needed; the sensor project's venv already has it
./venv/bin/python ../sensor/venv/bin/python tools/imu_log.py -t 20 --plot
# or:  pip3 install pyserial
python3 tools/imu_log.py -t 20 --plot
```

`imu_log.py` logs to CSV and prints the two things that matter at bring-up:

1. **Scale check** — `|acc|` must average ~**1.000 g** at rest. This is not
   ceremony: a framing/scaling mismatch in the earlier sensor project made it
   read 0.58–0.78 g, which silently poisons any filter built on top.
2. **Axis check** — per-axis mean/std/min/max swing, so rotating the board about
   one axis at a time shows you exactly which column responds. It also prints an
   accel-derived roll/pitch for the last sample.

## Firmware output

```
# I,t_ms,gx,gy,gz,ax,ay,az     raw int16 counts, gyro bias removed
I,1523,12,-4,7,410,-215,16250
# S,t_ms,gx,gy,gz,ax,ay,az     mdps and mg
S,1523,183,-61,107,50,-26,1983
```

`#` lines are comments; skip them when parsing.

## Commands (single line, newline-terminated)

| Cmd | Action |
|---|---|
| `?` | status: WHO_AM_I, address, samples/errors, gyro bias |
| `i` | rescan the I²C bus and re-probe the IMU |
| `r` / `s` / `x` | stream raw counts / scaled units / stop |
| `z` | **zero the gyro** — averages 200 samples while still |
| `c` | clear the gyro bias |
| `t` | one sample + die temperature |
| `O<a>,<g>` | set ODR codes, e.g. `O6,6` = 416 Hz both |
| `F<a>,<g>` | set full scale, e.g. `F2,1` = ±4 g, ±500 dps |

ODR codes: `0`=off `1`=12.5 `2`=26 `3`=52 `4`=104 `5`=208 `6`=416 `7`=833
`8`=1667 `9`=3333 `10`=6667 Hz.
Accel FS: `0`=2g `1`=16g `2`=4g `3`=8g. Gyro FS: `0`=250 `1`=500 `2`=1000 `3`=2000 dps.

## Register facts used (from ST's own driver header)

Taken from `ism330is_reg.h` as shipped inside MEMS Studio, not from memory:

```
WHO_AM_I  0x0F -> 0x22          CTRL1_XL 0x10   CTRL2_G 0x11
CTRL3_C   0x12  bit2 IF_INC, bit6 BDU
OUTX_L_G  0x22 .. 0x2D          gyro X/Y/Z then accel X/Y/Z, int16 LE
```

Gyro and accel outputs are **contiguous**, so a whole inertial sample is a single
12-byte burst read. `IF_INC` is what makes that legal and `BDU` prevents a sample
being torn by concurrent output refresh — both matter for a control loop that
polls this from a timer.

## Status

- Firmware **builds clean** (`-Wall -Wextra`), 9.1 KB flash / 2.6 KB RAM.
- **Not yet hardware-verified**: the timing of flashing it depends on the
  NUCLEO-C092RC being plugged in with the adapter wired per the table above.
  The first flash should be treated as a wiring test — `?` and `i` will report
  exactly what answered on the bus.
