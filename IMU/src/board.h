/*
 * board.h - NUCLEO-C092RC (STM32C092RC) <-> STEVAL-MKI230KA (ISM330IS) wiring
 *
 * The ISM330IS is the sensor on an STEVAL-MKI230KA DIL24 adapter. To use it we
 * take it OUT of the STEVAL-MKI109V3 socket and wire it to this MCU directly:
 * the MKI109V3's own firmware speaks a closed binary protocol (it only answers
 * MEMS Studio) and cannot be scripted, whereas a direct connection gives us raw
 * registers with nothing in between.
 *
 *   NUCLEO-C092RC            STEVAL-MKI230KA
 *   CN10 pin 3 = PB8  SCL -> sensor SCL / SPC
 *   CN10 pin 5 = PB9  SDA -> sensor SDA / SDI
 *   3V3                   -> VDD and VDDIO   (ISM330IS is 1.71-3.6 V)
 *   GND                   -> GND
 *
 *   SA0/SDO selects the address: 0x6A when low, 0x6B when high.
 *   Leave CS high (or unconnected) for I2C mode - CS low selects SPI.
 *
 * NOTE: the INA228/INA226 power module may share this bus. Its addresses
 * (0x45 / 0x41) do not collide with the ISM330IS (0x6A / 0x6B).
 *
 * Console: USART2 PA2/PA3 -> on-board ST-LINK V2-1 Virtual COM Port, 115200.
 *
 * MCU: Cortex-M0+ (ARMv6-M), 48 MHz, NO FPU -> all maths is integer.
 */
#ifndef BOARD_H
#define BOARD_H

/* ---- I2C bus ----
 * The IMU runs on **I2C2** so that the PMU keeps **I2C1** (PB8/PB9) to itself:
 * two independent peripherals, so the IMU never waits on the PMU's polling.
 *
 *   PB10 = I2C2_SCL  (AF14)   <- from the STM32C092RC datasheet AF table
 *   PB11 = I2C2_SDA  (AF14)
 *
 * Both pins are unused by the 6 motors, LEDs, button, USART2 and SWD, so this
 * costs nothing. (Do NOT use the PA9/PA10 I2C2 option here - PA10 is motor M6
 * in the MultiMotor pin map - and avoid PB3, which is SWO/JTDO.)
 */
#define IMU_I2C_INSTANCE    2u      /* 1 = I2C1 (PB8/PB9), 2 = I2C2 */
#define IMU_I2C_SCL_PORT    'B'
#define IMU_I2C_SCL_PIN     10u
#define IMU_I2C_SDA_PORT    'B'
#define IMU_I2C_SDA_PIN     11u
#define IMU_I2C_AF          14u     /* I2C2 on PB10/PB11 = AF14 */

/* I2C1 (PB8/PB9) is left free for the PM02D power module. */
#define I2C_AF              6u          /* I2C1 on PB8/PB9 = AF6 (UM3353 Tbl 13) */
#define I2C_AF_ALT          7u          /* fallback AF, probed automatically      */

/* 100 kHz standard mode, PCLK1 = 48 MHz. See PMU_C092RC/board.h for the
 * full timing derivation (PRESC/SCLL/SCLH chosen for 5.0/4.5 us). */
#define I2C_TIMINGR_VAL     0xB4201113u

/* ---- Console UART (ST-Link VCP) ---- */
#define CONSOLE_BAUD        115200U
#define UART_AF             1u          /* PA2/PA3 = USART2 = AF1 */
#define PCLK1_HZ            48000000u

/* ---- ISM330IS ---- */
#define ISM330IS_ADDR_LO    0x6Au       /* SA0/SDO = 0 */
#define ISM330IS_ADDR_HI    0x6Bu       /* SA0/SDO = 1 */
#define ISM330IS_WHO_AM_I   0x22u       /* value expected in WHO_AM_I (0x0F) */

/* Defaults: +-4 g and +-500 dps are sensible ranges for a small multirotor.
 * 416 Hz leaves headroom above a 500 Hz control loop without asking the
 * 100 kHz I2C bus for more than it can deliver. */
#define ISM330IS_DEF_XL_ODR 6u          /* 416 Hz  (HP mode) */
#define ISM330IS_DEF_G_ODR  6u          /* 416 Hz            */
#define ISM330IS_DEF_XL_FS  2u          /* +-4 g             */
#define ISM330IS_DEF_G_FS   1u          /* +-500 dps         */

/* Output rate of the CSV stream. A 12-byte burst on a 100 kHz bus costs
 * ~1.4 ms, so ~200 Hz is the practical ceiling here; 100 Hz is the default
 * because it is plenty for checking motion and for tuning a filter offline. */
#define IMU_PRINT_HZ        100u

#define GYRO_ZERO_SAMPLES   200u        /* samples averaged to find gyro bias */

#endif /* BOARD_H */
