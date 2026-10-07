#ifndef I2C_H
#define I2C_H

#include <stdint.h>

/* I2C1 master, PB8 = SCL, PB9 = SDA (AF4, open drain) */
void i2c_init(void);
int  i2c_ping(uint8_t addr7);                       /* 0 = device ACKs its address */
int  i2c_read_reg(uint8_t addr7, uint8_t reg, uint8_t *buf, uint32_t len);
int  i2c_write_reg16(uint8_t addr7, uint8_t reg, uint16_t value);

#endif /* I2C_H */
