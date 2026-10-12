#ifndef I2C_H
#define I2C_H

#include <stdint.h>

/* I2C1 master on PB8 = SCL, PB9 = SDA (default AF6, see board.h).
 * Returns 0 on success, negative on error. */
/* Select the I2C peripheral: 1 = I2C1 (PB8/PB9), 2 = I2C2 (e.g. PB10/PB11).
 * Enables that peripheral's clock. Independent of the pin choice below. */
void i2c_select(uint8_t instance);

void i2c_init_with_af(uint32_t af);
/* Put I2C1 on arbitrary pins (pin-probe mode, used when the adapter's pinout
 * is unknown). af 0..15 is swept by the caller when the AF is not known.
 * Returns 0 for valid pins, -1 for an unknown port letter. */
int  i2c_init_on_pins(char scl_port, uint8_t scl_pin,
                      char sda_port, uint8_t sda_pin, uint32_t af);
/* Same, but with an independent AF per pin - needed when the two signals only
 * reach the peripheral at different AF numbers (PB3=AF13 / PB4=AF14). */
int  i2c_init_on_pins2(char scl_port, uint8_t scl_pin, uint32_t scl_af,
                       char sda_port, uint8_t sda_pin, uint32_t sda_af);
int  i2c_ping(uint8_t addr7);
int  i2c_read_reg(uint8_t addr7, uint8_t reg, uint8_t *buf, uint32_t len);
int  i2c_write_reg16(uint8_t addr7, uint8_t reg, uint16_t value);
/* Single-byte register write (8-bit register + 8-bit value), e.g. IMU CTRL_*. */
int  i2c_write_reg8(uint8_t addr7, uint8_t reg, uint8_t value);
void i2c_bus_recover(void);

#endif /* I2C_H */
