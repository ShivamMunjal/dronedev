/*
 * board.h - NUCLEO-C092RC (STM32C092RC) <-> Holybro PM02D hardware mapping
 *
 * Wiring, confirmed against UM3353 Table 13 (ST morpho connector CN10):
 *
 *   CN10 pin 3 = PB8 = I2C1_SCL  -->  PM02D SCL
 *   CN10 pin 5 = PB9 = I2C1_SDA  -->  PM02D SDA
 *   CN10 pin 9/10 = GND          -->  PM02D GND
 *
 *   (PB8/PB9 are also on the Arduino header CN5 as SCL/D15 and SDA/D14.)
 *   Do NOT tie the PM's 5.2 V output to the Nucleo 5V pin while USB is attached.
 *
 * Console: USART2 PA2/PA3 -> on-board ST-LINK V2-1 Virtual COM Port.
 *
 * MCU: Cortex-M0+ (ARMv6-M), 48 MHz, NO FPU -> all maths is integer/fixed point.
 */
#ifndef BOARD_H
#define BOARD_H

/* ---- I2C bus ---- */
/* I2C1 alternate function on PB8/PB9 is AF6 (per ST's NUCLEO-C092RC examples) */
#define I2C_AF              6u
/* Fallback AF tried automatically if AF6 does not answer on the bus */
#define I2C_AF_ALT          7u
#define I2C_SPEED_HZ        100000u

/* TIMINGR for 100 kHz standard mode with I2C kernel clock = PCLK1 = 48 MHz:
 *   t_PRESC = (PRESC+1)/48MHz = 12/48MHz = 250 ns
 *   t_LOW   = (SCLL+1)  * t_PRESC = 20 * 250 ns = 5.00 us  (spec min 4.7 us)
 *   t_HIGH  = (SCLH+1)  * t_PRESC = 18 * 250 ns = 4.50 us  (spec min 4.0 us)
 *   -> ~105 kHz
 * SCLDEL = 4 -> 1250 ns >= t_r + t_SU;DAT = 1000 + 250 ns
 * SDADEL = 2 -> 500 ns  >= t_f + t_HD;DAT - t_SU;DAT
 */
#define I2C_TIMINGR_VAL     0xB4201113u

/* ---- Console UART (ST-Link VCP) ---- */
#define CONSOLE_BAUD        115200U
#define UART_AF             1u          /* PA2/PA3 = USART2 = AF1 */
#define PCLK1_HZ            48000000u   /* SYSCLK 48 MHz, APB1 prescaler = 1 */

/* ---- Power module electrical parameters ----------------------------------
 * Holybro PM02D (LV and HV) uses a 0.5 mOhm shunt:
 *   LV (6S)   : INA226 @ 0x41, +/-81.92 mV  -> 163.84 A
 *   HV (2S-12S, connected here) : INA228 @ 0x45, +/-163.84 mV -> 327.68 A
 */
#define R_SHUNT_UOHM        500u        /* 0.5 mOhm */

#define INA226_IMAX_MA      163840u     /* 163.84 A */
#define INA228_IMAX_MA      327680u     /* 327.68 A */

#define INA228_ADDR         0x45u
#define INA226_ADDR         0x41u

/* Telemetry loop timing */
#define SAMPLE_PERIOD_MS    100u        /* read the sensor at 10 Hz */
#define PRINT_PERIOD_MS     250u        /* print a CSV line at 4 Hz */

#endif /* BOARD_H */
