# MultiMotor_N6 — port of the drone firmware to STM32N6 (NUCLEO-N657X0-Q)

Port target: **NUCLEO-N657X0-Q** (MB1940), **STM32N657X0H3Q**, Cortex-M55,
600 MHz, 4.1 MB SRAM @ `0x34000000`, **no internal code flash** — boots from the
on-board 512 Mbit Octo-SPI flash.

Verified with CubeProgrammer v2.23: Device ID `0x486`, Rev Z, ST-LINK V3J17M10,
board recognised as `NUCLEO-N657X0-Q`.

Wiring: **[PINOUT.md](PINOUT.md)** (6 ESCs, I2C1, VCP, LEDs, boot switches).

---

## Port status

| # | Milestone | State |
|---|---|---|
| 0 | C092RC baseline backed up (`../_backup/firmware-C092RC-20261027/`) | ✅ |
| 1 | SDK vendored (CubeN6), chip/board/boot model understood | ✅ |
| 2 | Pinout derived (UM3417 + ST pin-data XML) | ✅ [PINOUT.md] |
| 3 | Makefile + build ST FSBL template with arm-gcc (`-mcpu=cortex-m55`) | ⬜ |
| 4 | VCP banner (USART1 PE5/PE6) → proves boot on hardware | ⬜ |
| 5 | Port console protocol (`? A D X M Q …`) + mixer to N6 | ⬜ |
| 6 | 6× PWM (TIM1/TIM14/TIM16 @500 Hz, 1000–2000 µs) | ⬜ |
| 7 | I2C1 (D14/D15) INA228 + ISM330IS, single bus | ⬜ |
| 8 | AHRS: MotionFX is **CM0P-only** → use portable Mahony 6-DOF for N6 | ⬜ |
| 9 | Dashboards talk to N6 (same protocol over VCP) | ⬜ |

## Boot & flash model (N6 specific)

Two images possible: **FSBL-only** (all code runs in SRAM @ `0x34180400`,
511 KB — simplest, one image) or **FSBL + XIP Appli** (app executes in external
flash @ `0x70100400`). Both need a **trusted header**:

```bash
CP=/opt/ST/STM32CubeCLT_1.22.0/STM32CubeProgrammer/bin
$CP/STM32_SigningTool_CLI -bin build/FSBL.bin -nk -of 0x80000000 -t fsbl \
    -o build/FSBL-trusted.bin -hv 2.3 -dump build/FSBL-trusted.bin

$CP/STM32_Programmer_CLI -c port=SWD mode=UR \
    -el MX25UM51245G_STM32N6570-NUCLEO.stldr \
    -w build/FSBL-trusted.bin 0x70000000 -align 4 -v -rst
```
XIP application (if used) is written **`FSBL-trusted @0x70000000`** and
**`Appli-trusted @0x70100000`**. Boot switches: **BOOT0 1-2, BOOT1 1-2**.

`st-info`/`st-flash` do **not** understand this chip (chipid 0x000) — always use
`STM32_Programmer_CLI`.

## Vendored (gitignored)

* `CubeN6/` — STMicroelectronics/STM32CubeN6 (CMSIS device, HAL, templates).
* `open_pin_data/` — STMicroelectronics/STM32_open_pin_data (MCU AF + board data).

## Key deltas vs the C092RC port

| | C092RC | N657 |
|---|---|---|
| core | Cortex-M0+ 48 MHz, no FPU | Cortex-M55 600 MHz, FPU **fpv5-d16** |
| flash | 256 KB internal | external XSPI (signed header!) |
| RAM | 30 KB | 4.1 MB @0x34000000 |
| console | USART2 PA2/PA3 | **USART1 PE5/PE6 (VCP)** |
| motors | TIM16/17/14/1 ×6 | **TIM1×4 (PE9,PE11,PF6,PC12) + TIM14 (PG2) + TIM16 (PA3)** |
| sensors | I2C1 PMU + I2C2 IMU | **single I2C1 (D14/D15)** with both |
| AHRS | MotionFX CM0P `.a` | portable Mahony (MotionFX has no M55 build) |
