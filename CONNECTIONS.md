# DroneProject — Complete Connections (NUCLEO-C092RC)

Master wiring reference for the whole stack: **6 motors (ESC)** + **PMU (PM02D)**
+ **IMU (ISM330IS)** on the one NUCLEO-C092RC (STM32C092RCT6). Everything is
wired at the same time — the three subsystems use **disjoint pins**.

MCU: Cortex-M0+, 30 KB SRAM, 256 KB flash. Console = USART2 PA2/PA3 → ST-Link VCP.

---

## 1. Master pin map (all subsystems)

| Function | MCU pin | Arduino header | ST morpho | Peripheral / AF | Bus |
|---|---|---|---|---|---|
| **M1** ESC | PA6 | D12 (CN5-5) | CN10-13 | TIM16_CH1 / AF5 | PWM |
| **M2** ESC | PA7 | D11 (CN5-4) | CN10-15 | TIM17_CH1 / AF5 | PWM |
| **M3** ESC | PA4 | A2  (CN8-3) | CN10-21 | TIM14_CH1 / AF4 | PWM |
| **M4** ESC | PA8 | D7  (CN5-6) | CN10-18 | TIM1_CH1 / AF2 | PWM |
| **M5** ESC | PA1 | A1  (CN8-2) | CN10-16 | TIM1_CH2 / AF5 | PWM |
| **M6** ESC | PA10 | D2 (CN5-2) | CN10-14 | TIM1_CH3 / AF2 | PWM |
| **PMU SCL** | PB8 | D15 (CN5-10) | **CN10-3** | I2C1_SCL / AF6 | I2C1 |
| **PMU SDA** | PB9 | D14 (CN5-9) | **CN10-5** | I2C1_SDA / AF6 | I2C1 |
| **IMU SCL** | PB10 | — | **CN10-34** | I2C2_SCL / AF6 | I2C2 |
| **IMU SDA** | PB11 | — | **CN7-37** | I2C2_SDA / AF6 | I2C2 |
| Console TX | PA2 | D1 (CN9-2) | CN10-31 | USART2_TX / AF1 | VCP |
| Console RX | PA3 | D0 (CN10-22) | CN10-22 | USART2_RX / AF1 | VCP |
| E-stop button | PC13 | USER BTN | on-board | GPIO in | — |
| GND | GND | GND | CN10-9/10 | common | — |

> **Key fact:** the PMU owns **I2C1** and the IMU owns **I2C2** — two separate
> peripherals, so they never share a bus and never wait on each other.

---

## 2. Motors / ESCs (MultiMotor firmware)

6 ESC signal outputs. ESCs take battery power separately; only **signal** comes
from the MCU. Common GND is mandatory.

| Motor | Signal pin | Header | ESC wire |
|---|---|---|---|
| M1 | PA6 | D12 | ESC 1 signal |
| M2 | PA7 | D11 | ESC 2 signal |
| M3 | PA4 | A2  | ESC 3 signal |
| M4 | PA8 | D7  | ESC 4 signal |
| M5 | PA1 | A1  | ESC 5 signal |
| M6 | PA10 | D2 | ESC 6 signal |

```
NUCLEO PA6 ──────► ESC1 signal ──────► Motor 1
NUCLEO PA7 ──────► ESC2 signal ──────► Motor 2
NUCLEO PA4 ──────► ESC3 signal ──────► Motor 3
NUCLEO PA8 ──────► ESC4 signal ──────► Motor 4
NUCLEO PA1 ──────► ESC5 signal ──────► Motor 5
NUCLEO PA10 ─────► ESC6 signal ──────► Motor 6
Battery + ───────► ESC power (BEC feeds motors)
GND (all) ───────► common ground
```

Default mixer geometry (Hexa-X) — angle, yaw-dir:

| Motor | Pin | Angle | dir |
|---|---|---|---|
| M1 | PA6 | 30° | -1 |
| M2 | PA7 | 90° | +1 |
| M3 | PA4 | 210° | +1 |
| M4 | PA8 | 270° | -1 |
| M5 | PA1 | 150° | -1 |
| M6 | PA10 | 330° | +1 |

**Do NOT** tie the PMU's 5.2 V output to the Nucleo 5 V pin while USB is attached.

---

## 3. PMU — Holybro PM02D (INA228 / INA226) on **I2C1**

| PM02D | NUCLEO | Pin |
|---|---|---|
| SCL | I2C1_SCL | **PB8** = CN10-3 (or D15) |
| SDA | I2C1_SDA | **PB9** = CN10-5 (or D14) |
| GND | GND | CN10-9/10 |
| 5.2 V out | (leave) | do not tie to Nucleo 5 V with USB |

* 0.5 mΩ shunt. Auto-detects **INA228 @0x45 (HV)** or **INA226 @0x41 (LV)**.
* I2C1 AF6 (falls back to AF7, auto-probed).

```
PM02D 6-pin I2C cable          NUCLEO-C092RC
  SCL      ------------------>  CN10 pin 3  (PB8)
  SDA      ------------------>  CN10 pin 5  (PB9)
  GND      ------------------>  CN10 pin 9/10
```

---

## 4. IMU — ISM330IS (STEVAL-MKI230KA) on **I2C2**

Two boards are required: the **STEVAL-MKI230A** sensor board + the
**STEVAL-MKIGIBV5** DIL24 adapter (the GIBV5 is only wiring; it has no sensor).
Join them with the kit flat cable.

| Signal | NUCLEO | Pin |
|---|---|---|
| SCL | I2C2_SCL | **PB10** = CN10-34 (morpho) |
| SDA | I2C2_SDA | **PB11** = CN7-37 (morpho) |
| VDD, VDDIO | 3V3 | 3V3 |
| GND | GND | GND |
| CS | **3V3** | must be HIGH or I2C is disabled |
| SA0/SDO | **GND** | → address **0x6A** (verified) |

> `CS` low selects SPI and silences I2C — always tie CS to 3V3.
> `SA0/SDO` = GND → 0x6A; = 3V3 → 0x6B. Both are probed, so either works.

### DIL24 adapter breakout (MKIGIBV5)

| DIL24 pin | Signal | Connect to |
|---|---|---|
| 1 | VDD | 3V3 |
| 2 | VDDIO | 3V3 |
| 3,4,5,6 | OCS, SCX, SDX, OSDO | unused (ISM330IS) |
| 14 | INT1 | unused |
| 15 | INT2 | unused |
| **19** | **CS** | **3V3** (HIGH) |
| **20** | **SCL** | PB10 (CN10-34) |
| **21** | **SDA** | PB11 (CN7-37) |
| **22** | **SDO/SA0** | GND = 0x6A |
| 7–13, 16–18, 23 | – | unused |
| **24** | GND | GND |

```
STEVAL-MKI230KA / MKIGIBV5         NUCLEO-C092RC
  SCL  (DIL24 pin 20)  ---------->  CN10 pin 34  (PB10)
  SDA  (DIL24 pin 21)  ---------->  CN7  pin 37  (PB11)
  VDD  (pin 1)  ────────────────►  3V3
  VDDIO(pin 2)  ────────────────►  3V3
  CS   (pin 19) ────────────────►  3V3   (must be HIGH)
  SDO  (pin 22) ────────────────►  GND   (= address 0x6A)
  GND  (pin 24) ────────────────►  GND
```

---

## 5. Free / reserved pins

| Pin | Status |
|---|---|
| PA9, PB4 | Arduino I2C2 alt preset (D8 SCL / D5 SDA) — only if you switch `IMU_I2C_CFG_ARDUINO` |
| PB13/PB14 | other I2C2 candidate pair (probe mode) |
| PA2/PA3 | USART2 console — reserved |
| PC13 | user button (e-stop) |
| PA5 (LD4) | on-board LED |
| PB8/PB9 | I2C1 (PMU) — leave free of IMU |

> The IMU firmware auto-scans several I2C2 pin pairs at boot and locks onto the
> one where a `WHO_AM_I == 0x22` answers, so mis-plugging is reported rather
> than silent.

---

## 6. Firmware ↔ subsystems

| Firmware | Uses | Image |
|---|---|---|
| `MultiMotor/` | motors (TIM PWM) + PMU (I2C1) | `MultiMotor.elf` |
| `IMU/` | IMU (I2C2) + MotionFX fusion | `imu_ism330is_c092rc.elf` |

The MCU runs **one image at a time**. Wiring is pin-compatible for all three at
once (no overlap), but cross-fusion (IMU on the motor board) is future work —
the natural target is PB10/PB11 (I2C2), already reserved for it here.

---

## 7. Grounds & power — the rules

1. **Common GND** across NUCLEO, ESCs, PMU, IMU. No exceptions.
2. ESCs are powered from the **battery**, not the Nucleo. Signal only to MCU.
3. Never tie the PM02D **5.2 V** output to the Nucleo 5 V while USB is attached.
4. PMU and IMU are **3.3 V** logic (ISM330IS is 1.71–3.6 V) — feed 3V3, not 5V.
5. IMU `CS` must be **3V3** (HIGH) for I2C to work at all.
