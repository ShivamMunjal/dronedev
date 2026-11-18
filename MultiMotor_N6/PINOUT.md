# NUCLEO-N657X0-Q (MB1940) — hexacopter wiring / test pinout

Port target board. MCU **STM32N657X0H3Q**, Cortex-M55 @ 600 MHz, VFBGA264.
Source of truth: **UM3417 Rev 4** (STM32N6 Nucleo-144 board MB1940) + ST
`STM32_open_pin_data` (`mcu/STM32N657X0HxQ.xml`), cross-checked per pin for a
valid timer/I2C alternate function.

> Ground rule: **every ESC / sensor GND must tie to the Nucleo GND** (common
> ground). Digital I/O is **3.3 V** — drive ESCs with signal + GND only.

---

## 0. Before powering — boot mode (boot switches)

The N657 has **no internal code flash**: the FSBL is loaded from the **external
Octo-SPI flash (512 Mbit)** by the BootROM, then jumps to the application.

| Mode | BOOT0 | BOOT1 |
|---|---|---|
| **Boot from external flash (normal run)** ← use this | **1-2** | **1-2** |
 Development mode (debug, code runs from SRAM via debugger) | x | 2-3 |

Flash order/addresses (from the CubeN6 template readme, CubeProgrammer ≥2.21 → add `-align 4`):

```
FSBL-trusted.bin  @ 0x70000000   (external XSPI flash base)
Appli-trusted.bin @ 0x70100000   (app executes at 0x70100400, past its header)
external loader   : MX25UM51245G_STM32N6570-NUCLEO.stldr
signing           : STM32_SigningTool_CLI -bin X.bin -nk -of 0x80000000 -t fsbl -o X-trusted.bin -hv 2.3
```

---

## 1. Console (no wiring needed)

| Function | Connector | MCU pin | Notes |
|---|---|---|---|
| **VCP TX/RX** | ST-LINK USB (CN10) | **PE5 (TX) / PE6 (RX)**, USART1 AF7 | 115200 8N1 → `/dev/cu.usbmodem1102` |

PE5/PE6 are also on morpho **CN15-4 (PE5)** / **CN15-2 (PE6)** — already wired
to the ST-LINK-V3EC, do **not** re-drive them.

## 2. Motor ESCs — 6× PWM (Arduino header, all direct TIM outputs)

| Motor | Arduino | MCU pin | Timer / channel |
|---|---|---|---|
| **M1** | **D3** | PE9  | **TIM1_CH1** |
| **M2** | **D7** | PE11 | **TIM1_CH2** |
| **M3** | **A2** | PF6  | **TIM1_CH3** |
| **M4** | **A4** | PC12 | **TIM1_CH4** |
| **M5** | **D11** | PG2 | **TIM14_CH1** |
| **M6** | **D10** | PA3 | **TIM16_CH1** |

* All six are **direct** channels (no complementary `_N` outputs), so duty is not
  inverted; all four TIM1 channels share one timer → identical 500 Hz period,
  exactly like the C092 build.
* Spares with a timer (if you move a motor): **D12 = PG1 = TIM13_CH1**,
  **D9 = PD7 = TIM1_CH2** (would clash with PE11 — only one pin may route a
  given timer channel), **D5/D6 = TIM1_CH2N/TIM1_CH4N** (usable with CCxNP=0).
* **A4 note:** default solder-bridge state gives A4 = PC12 (digital, 3.3 V) —
  that is what we use. `PC1` is only selected on A4 if SB2/SB4 are re-soldered
  (I2C1 mode) — we do **not** do that.
* **Do not use D13**: LD3 green LED net (PE15/PB15).

**ESC wiring per motor:** signal (white) → Arduino pin above, ESC GND (black) →
GND. **Leave the ESC BEC red wire disconnected** (do not back-feed 5 V into the
board while it is USB-powered; power the pack separately and share GND).

## 3. I2C bus (PMU + IMU on ONE bus)

| Function | Arduino | MCU pin | AF |
|---|---|---|---|
| **I2C1 SDA** | **D14** | PC1  | I2C1_SDA |
| **I2C1 SCL** | **D15** | PH9  | I2C1_SCL |

| Device | Address | Wiring |
|---|---|---|
| **INA228 / PM02D PMU** | `0x40` (A0/A1 set by board) | SDA→D14, SCL→D15, VCC→3V3, GND→GND |
| **ISM330IS IMU** | `0x6A` (SA0=GND, CS→3V3 for I2C mode) | SDA→D14, SCL→D15, VDD→3V3, GND→GND |

* Two addresses on one bus — no conflict; the N6 port drives **one** I2C1
  instead of the C092's two buses (small driver change, see README).
* **Pull-ups:** the MB1940 does not document pull-ups on D14/D15 — add
  **4.7 kΩ to 3V3** if your breakout boards don't already have them.
* **Avoid I2C2 (PB10/PB11):** on this board they belong to the USB Type-C
  PD controller (CN8) and are not on any header.

## 4. Power, ground, control

| Function | Where | Notes |
|---|---|---|
| **3V3 out** | Arduino **CN5 pin 4** (also CN3-16) | powers IMU/PMU modules |
| **5V** | CN5 pin 5 / CN3-6 | ESC BEC only if board NOT USB-powered |
| **GND** | CN5 pins **6,7** / CN3-19,20 | common with ESC + sensors |
| **VIN (7-12 V)** | CN5 pin 8 / CN3-24 | optional external supply |
| **E-stop / user button** | **B1 = PC13** (active HIGH, on-board) | also morpho CN3-23 |
| **Reset** | B2 (NRST) / CN5 pin 3 | |
| **LED LD6 green** | PG0 (active LOW) | status "armed/alive" LED |
| **LED LD7 blue** | PG8 (active LOW) | |
| **LED LD5 red** | PG10 (active LOW) | error/kill LED |
| **LED LD3 green** | PB15 (Arduino D13 net) | |

## 5. Pins to leave alone

| Pins | Why |
|---|---|
| PE5, PE6 (CN15-4/-2) | ST-LINK VCP |
| PB10, PB11 | USB Type-C PD controller (not on headers anyway) |
| PH0/PH1 | HSE oscillator |
| CN16 `PO0-7 / PP0-15` | board-internal parallel signals, not MCU GPIO |
| PF7/PF4/PG11/PF10/PF14/PF15/PF11/PF12/PF13 | Ethernet RMII |

## 6. First-power test sequence (after flashing, see ../README.md)

1. BOOT0=1-2, BOOT1=1-2, press **B2** → LD6 (PG0) should blink.
2. `ls /dev/cu.usbmodem1102 && screen /dev/cu.usbmodem1102 115200` → banner.
3. Scan I2C: firmware `?`/scan should see `0x40` (INA228) + `0x6A` (ISM330IS).
4. `M`/geometry → verify each ESC: motors must be **props-off** for tests.
5. `A` arm with pack connected, throttle at minimum.
