#ifndef I2C_H
#define I2C_H

#include <stdint.h>

/* I2C1 master on PB8 = SCL, PB9 = SDA (default AF6, see board.h).
 * Returns 0 on success, negative on error. */
void i2c_init_with_af(uint32_t af);
int  i2c_ping(uint8_t addr7);
int  i2c_read_reg(uint8_t addr7, uint8_t reg, uint8_t *buf, uint32_t len);
int  i2c_write_reg16(uint8_t addr7, uint8_t reg, uint16_t value);
void i2c_bus_recover(void);

#endif /* I2C_H */
