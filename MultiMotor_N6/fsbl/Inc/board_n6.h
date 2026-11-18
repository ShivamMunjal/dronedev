/* board_n6.h — NUCLEO-N657X0-Q pin map + peripheral handles for MultiMotor_N6
 *
 * Pin choices come from UM3417 (MB1940) and were AF-verified against ST's
 * STM32N6 GPIO mode database (STM32_open_pin_data/mcu/IP/GPIO-STM32N6_gpio_v1_0_Modes.xml).
 */
#ifndef BOARD_N6_H
#define BOARD_N6_H

#include <stdint.h>
#include "stm32n6xx_hal.h"

/* ── Motors: 6 x PWM @ 500 Hz, 1000..2000 us ────────────────────────────── */
typedef struct {
    GPIO_TypeDef *port;
    uint16_t      pin;
    uint8_t       af;
    TIM_TypeDef  *tim;
    uint32_t      chan;      /* TIM_CHANNEL_x */
} n6_motor_t;

#define N6_MOTOR_COUNT 6

/* M1..M6 -> Arduino D3, D7, A2, A4, D11, D10 */
extern const n6_motor_t n6_motors[N6_MOTOR_COUNT];

void n6_pwm_init(void);
void n6_pwm_set(uint8_t idx, uint16_t us);

/* ── I2C1: PMU (INA228 @0x40) + IMU (ISM330IS @0x6A) on one bus ─────────── */
#define N6_I2C_SDA_PORT   GPIOC    /* Arduino D14 = PC1  */
#define N6_I2C_SDA_PIN    GPIO_PIN_1
#define N6_I2C_SCL_PORT   GPIOH    /* Arduino D15 = PH9  */
#define N6_I2C_SCL_PIN    GPIO_PIN_9
#define N6_I2C_AF         GPIO_AF4_I2C1

extern I2C_HandleTypeDef n6_hi2c1;

void n6_i2c_init(uint32_t speed_hz);
int  n6_i2c_write(uint8_t addr7, const uint8_t *buf, uint16_t len, uint32_t to_ms);
int  n6_i2c_read(uint8_t addr7, uint8_t *buf, uint16_t len, uint32_t to_ms);
int  n6_i2c_mem_read(uint8_t addr7, uint8_t reg, uint8_t *buf, uint16_t len);
int  n6_i2c_mem_write(uint8_t addr7, uint8_t reg, const uint8_t *buf, uint16_t len);
int  n6_i2c_probe(uint8_t addr7);

/* ── Console (USART1 VCP) ───────────────────────────────────────────────── */
void n6_uart_init(void);
void n6_tx(const char *s);
void n6_tx_char(char c);
void n6_tx_uint(uint32_t v);
void n6_tx_int(int32_t v);
int  n6_rx_char(char *c);
void n6_led_set(int pin, int on);
int  n6_led_get(int pin);
extern UART_HandleTypeDef huart1;

#endif /* BOARD_N6_H */
