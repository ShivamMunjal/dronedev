/**
 * pmu_config.h — hardware constants for the PM02D power module on this board
 *
 * NUCLEO-C092RC wiring (free pins — the six ESC outputs use PA1/PA4/PA6/PA7/PA8/PA10):
 *     PB8 = I2C1_SCL  -> PM02D SCL   (CN10 pin 3)
 *     PB9 = I2C1_SDA  -> PM02D SDA   (CN10 pin 5)
 *     GND             -> PM02D GND
 *
 * Do NOT connect the PM's 5.2 V output to the Nucleo 5 V pin while USB is attached.
 */
#ifndef PMU_CONFIG_H
#define PMU_CONFIG_H

/* ── I2C1 ────────────────────────────────────────────────────────────── */
#define I2C_AF              6u          /* AF6 = I2C1 on PB8/PB9  (ST's NUCLEO-C092RC MSP) */
#define I2C_AF_ALT          7u          /* fallback tried if AF6 does not answer           */
#define I2C_SPEED_HZ        100000u

/* TIMINGR for 100 kHz with the I2C kernel clock = PCLK1 = 48 MHz:
 *   t_PRESC = 12/48MHz = 250 ns
 *   t_LOW   = 20 * 250 ns = 5.00 us   (standard mode min 4.7 us)
 *   t_HIGH  = 18 * 250 ns = 4.50 us   (standard mode min 4.0 us)
 */
#define I2C_TIMINGR_VAL     0xB4201113u

/* ── Power module ────────────────────────────────────────────────────────
 * Holybro PM02D, both variants use a 0.5 mOhm shunt:
 *   LV  (6S)    : INA226 @ 0x41 -> 163.84 A
 *   HV  (2S-12S): INA228 @ 0x45 -> 327.68 A   <- the HV module
 */
#define R_SHUNT_UOHM        500u
#define INA226_IMAX_MA      163840u
#define INA228_IMAX_MA      327680u
#define INA228_ADDR         0x45u
#define INA226_ADDR         0x41u

#endif /* PMU_CONFIG_H */
