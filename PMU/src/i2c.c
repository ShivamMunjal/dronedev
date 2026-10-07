/*
 * i2c.c - bare-metal polling I2C1 master for STM32F4.
 *
 * Every wait has a bounded spin count so a missing/stuck peripheral can never
 * hang the firmware; a failure triggers a peripheral reset plus a bus
 * un-wedge (9 clock pulses) and the transfer is retried once by the caller.
 */
#include "stm32f4xx.h"
#include "board.h"
#include "i2c.h"
#include "uart.h"
#include "system.h"

#define I2Cx             I2C1
#define I2C_TIMEOUT      200000u

static uint32_t s_pclk1_hz = 42000000u;

/* Wait until (reg & mask) == expected. Returns 0 on success, -1 on timeout. */
static int wait_flag(volatile uint32_t *reg, uint32_t mask, uint32_t expected)
{
    for (uint32_t i = 0; i < I2C_TIMEOUT; i++) {
        if ((*reg & mask) == expected) {
            return 0;
        }
    }
    return -1;
}

static void i2c_hw_setup(void)
{
    I2Cx->CR1 = 0u;                                  /* disable to reconfigure */
    I2Cx->CR1 |= I2C_CR1_SWRST;
    I2Cx->CR1 &= ~I2C_CR1_SWRST;

    I2Cx->CR2 = (s_pclk1_hz / 1000000u) & I2C_CR2_FREQ_Msk;  /* FREQ in MHz */
    /* Standard mode: CCR = PCLK / (2 * 100 kHz), TRISE = PCLK[MHz] + 1 */
    I2Cx->CCR = (s_pclk1_hz / (2u * I2C_SPEED_HZ)) & I2C_CCR_CCR;
    I2Cx->TRISE = ((s_pclk1_hz / 1000000u) + 1u) & I2C_TRISE_TRISE;
    I2Cx->OAR1 = 0x4000u;                            /* master only           */
    I2Cx->OAR2 = 0u;
    I2Cx->CR1 = I2C_CR1_PE | I2C_CR1_ACK;
}

/* Clock out up to 9 pulses on SCL to free a slave that is holding SDA low. */
static void i2c_bus_recover(void)
{
    I2Cx->CR1 &= ~I2C_CR1_PE;                        /* release the pins      */
    GPIOB->MODER = (GPIOB->MODER & ~(GPIO_MODER_MODER8 | GPIO_MODER_MODER9)) |
                   (1u << GPIO_MODER_MODER8_Pos) | (1u << GPIO_MODER_MODER9_Pos);
    GPIOB->OTYPER |= GPIO_OTYPER_OT8 | GPIO_OTYPER_OT9;   /* open drain       */
    GPIOB->BSRR = GPIO_BSRR_BS8 | GPIO_BSRR_BS9;          /* both released    */

    for (int i = 0; i < 9; i++) {
        GPIOB->BSRR = GPIO_BSRR_BR8;                 /* SCL low            */
        delay_us(5);
        GPIOB->BSRR = GPIO_BSRR_BS8;                 /* SCL high           */
        delay_us(5);
    }
    /* Generate a STOP: SDA low -> high while SCL is high */
    GPIOB->BSRR = GPIO_BSRR_BR9;
    delay_us(5);
    GPIOB->BSRR = GPIO_BSRR_BS8;
    delay_us(5);
    GPIOB->BSRR = GPIO_BSRR_BS9;
    delay_us(5);

    /* back to AF4 open-drain */
    GPIOB->MODER = (GPIOB->MODER & ~(GPIO_MODER_MODER8 | GPIO_MODER_MODER9)) |
                   (2u << GPIO_MODER_MODER8_Pos) | (2u << GPIO_MODER_MODER9_Pos);
    i2c_hw_setup();
}

void i2c_init(void)
{
    /* --- clocks --- */
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOBEN;
    RCC->APB1ENR |= RCC_APB1ENR_I2C1EN;

    /* --- PB8 = I2C1_SCL, PB9 = I2C1_SDA, AF4, open drain, internal pull-ups ---
     * The PM02D carries its own pull-ups; the weak internal ones are only a
     * safety net. Add 2k2..4k7 to 3V3 if your module has none.
     */
    GPIOB->MODER = (GPIOB->MODER & ~(GPIO_MODER_MODER8 | GPIO_MODER_MODER9)) |
                   (2u << GPIO_MODER_MODER8_Pos) | (2u << GPIO_MODER_MODER9_Pos);
    GPIOB->OTYPER |= GPIO_OTYPER_OT8 | GPIO_OTYPER_OT9;
    GPIOB->OSPEEDR |= (3u << GPIO_OSPEEDR_OSPEED8_Pos) | (3u << GPIO_OSPEEDR_OSPEED9_Pos);
    GPIOB->PUPDR = (GPIOB->PUPDR & ~(GPIO_PUPDR_PUPDR8 | GPIO_PUPDR_PUPDR9)) |
                   (1u << GPIO_PUPDR_PUPD8_Pos) | (1u << GPIO_PUPDR_PUPD9_Pos);
    GPIOB->AFR[1] = (GPIOB->AFR[1] & ~((0xFu << 0) | (0xFu << 4))) |
                    (4u << 0) | (4u << 4);

    i2c_hw_setup();

    /* free a stuck bus (slave left mid-transfer) */
    if (I2Cx->SR2 & I2C_SR2_BUSY) {
        i2c_bus_recover();
    }
}

/* START + address phase. rw = 0 write, 1 read. */
static int i2c_start(uint8_t addr7, uint8_t rw)
{
    I2Cx->CR1 |= I2C_CR1_START;
    if (wait_flag(&I2Cx->SR1, I2C_SR1_SB, I2C_SR1_SB) != 0) {
        return -1;
    }

    I2Cx->DR = (uint32_t)((addr7 << 1) | (rw & 1u));

    for (uint32_t i = 0; i < I2C_TIMEOUT; i++) {
        uint32_t sr1 = I2Cx->SR1;
        if (sr1 & I2C_SR1_ADDR) {
            (void)I2Cx->SR1;             /* clear ADDR: read SR1 ... */
            (void)I2Cx->SR2;             /* ... then SR2            */
            return 0;
        }
        if (sr1 & I2C_SR1_AF) {          /* NACK: no such device    */
            I2Cx->SR1 &= ~I2C_SR1_AF;
            I2Cx->CR1 |= I2C_CR1_STOP;
            return -2;
        }
    }
    return -1;
}

static void i2c_stop(void)
{
    I2Cx->CR1 |= I2C_CR1_STOP;
    /* wait for the bus to go idle so the next START is legal */
    for (uint32_t i = 0; i < I2C_TIMEOUT; i++) {
        if ((I2Cx->SR2 & I2C_SR2_BUSY) == 0u) {
            break;
        }
    }
}

int i2c_ping(uint8_t addr7)
{
    if (i2c_start(addr7, 0) != 0) {
        return -1;
    }
    i2c_stop();
    /* address-only probes with no data byte leave TXE/BTF set; clear state */
    (void)I2Cx->SR1;
    (void)I2Cx->SR2;
    return 0;
}

int i2c_write_reg16(uint8_t addr7, uint8_t reg, uint16_t value)
{
    int rc = i2c_start(addr7, 0);
    if (rc != 0) {
        return rc;
    }

    if (wait_flag(&I2Cx->SR1, I2C_SR1_TXE, I2C_SR1_TXE) != 0) {
        return -1;
    }
    I2Cx->DR = reg;

    if (wait_flag(&I2Cx->SR1, I2C_SR1_TXE, I2C_SR1_TXE) != 0) {
        return -1;
    }
    I2Cx->DR = (value >> 8) & 0xFFu;      /* INA2xx registers are big endian */

    if (wait_flag(&I2Cx->SR1, I2C_SR1_TXE, I2C_SR1_TXE) != 0) {
        return -1;
    }
    I2Cx->DR = value & 0xFFu;

    if (wait_flag(&I2Cx->SR1, I2C_SR1_BTF, I2C_SR1_BTF) != 0) {
        return -1;
    }
    i2c_stop();
    return 0;
}

int i2c_read_reg(uint8_t addr7, uint8_t reg, uint8_t *buf, uint32_t len)
{
    if (len == 0u) {
        return -1;
    }

    /* --- phase 1: write the register pointer --- */
    int rc = i2c_start(addr7, 0);
    if (rc != 0) {
        return rc;
    }
    if (wait_flag(&I2Cx->SR1, I2C_SR1_TXE, I2C_SR1_TXE) != 0) {
        return -1;
    }
    I2Cx->DR = reg;
    if (wait_flag(&I2Cx->SR1, I2C_SR1_BTF, I2C_SR1_BTF) != 0) {
        return -1;
    }

    /* --- phase 2: repeated START, read --- */
    I2Cx->CR1 |= I2C_CR1_START;
    if (wait_flag(&I2Cx->SR1, I2C_SR1_SB, I2C_SR1_SB) != 0) {
        return -1;
    }
    I2Cx->CR1 |= I2C_CR1_ACK;
    I2Cx->DR = (uint32_t)((addr7 << 1) | 1u);
    if (wait_flag(&I2Cx->SR1, I2C_SR1_ADDR, I2C_SR1_ADDR) != 0) {
        return -1;
    }
    (void)I2Cx->SR1;
    (void)I2Cx->SR2;

    for (uint32_t i = 0; i < len; i++) {
        if (i == (len - 1u)) {            /* NACK + STOP for the final byte */
            I2Cx->CR1 &= ~I2C_CR1_ACK;
            I2Cx->CR1 |= I2C_CR1_STOP;
        }
        if (wait_flag(&I2Cx->SR1, I2C_SR1_RXNE, I2C_SR1_RXNE) != 0) {
            return -1;
        }
        buf[i] = (uint8_t)I2Cx->DR;
    }

    for (uint32_t i = 0; i < I2C_TIMEOUT; i++) {
        if ((I2Cx->SR2 & I2C_SR2_BUSY) == 0u) {
            break;
        }
    }
    I2Cx->CR1 |= I2C_CR1_ACK;
    return 0;
}
