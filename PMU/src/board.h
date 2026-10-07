/*
 * board.h - Nucleo-F401RE <-> Holybro PM02D hardware mapping
 *
 *  Nucleo-F401RE            Holybro PM02D (6-pin I2C connector)
 *  ----------------------   --------------------------------
 *  PB8  (I2C1_SCL, AF4) --> SCL
 *  PB9  (I2C1_SDA, AF4) --> SDA
 *  GND                  --> GND
 *  (do NOT connect the PM's 5.2V output to the Nucleo 5V pin while USB is
 *   attached - power the board from USB only)
 *
 *  PA2  (USART2_TX, AF7) -> ST-Link Virtual COM Port (115200 8N1)
 *  PA3  (USART2_RX, AF7) <- ST-Link Virtual COM Port
 */
#ifndef BOARD_H
#define BOARD_H

/* ---- I2C bus ---- */
#define I2C_INSTANCE        1U
#define I2C_SPEED_HZ        100000U

/* ---- Console UART (ST-Link VCP) ---- */
#define CONSOLE_BAUD        115200U

/* ---- Power module electrical parameters ---------------------------------
 * Holybro PM02D (both LV and HV variants) uses a 0.5 mOhm shunt.
 *   LV (6S)  variant : INA226 @ 0x41, +/-81.92 mV shunt range -> 163.84 A
 *   HV (2S-12S, this one) : INA228 @ 0x45, +/-163.84 mV shunt range -> 327.68 A
 * Change R_SHUNT_UOHM if you own a module with a different shunt.
 */
#define R_SHUNT_UOHM        500u          /* shunt = 0.5 mOhm = 500 uOhm */

/* Full-scale current used to size the calibration registers.
 * 0.5 mOhm + INA226 (+/-81.92 mV)  -> 163.84 A
 * 0.5 mOhm + INA228 (+/-163.84 mV) -> 327.68 A */
#define INA226_IMAX_MA      163840u       /* 163.84 A */
#define INA228_IMAX_MA      327680u       /* 327.68 A */

/* Expected addresses, tried in this order (HV first) */
#define INA228_ADDR         0x45u
#define INA226_ADDR         0x41u

/* Telemetry loop timing */
#define SAMPLE_PERIOD_MS    100u          /* read the sensor at 10 Hz      */
#define PRINT_PERIOD_MS     250u          /* print a CSV line at 4 Hz      */

#endif /* BOARD_H */
