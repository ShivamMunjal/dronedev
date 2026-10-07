/*
 * i2c.c - bare-metal polling I2C1 master for STM32C0 (I2C "v2" peripheral:
 * TIMINGR + CR2 command register + ISR/ICR flags + TXDR/RXDR data).
 *
 * This is a different peripheral generation from the STM32F4 (which used
 * CR2/FREQ + SR1/SR2 + DR), so the master state machine is implemented here
 * directly rather than via HAL:
 *
 *   write : CR2 = SADD|NBYTES|AUTOEND|START, fill TXDR on TXIS, wait STOPF
 *   read  : CR2 = SADD|NBYTES=1|START (send reg pointer, AUTOEND=0)
 *           wait TC  -> bus is stretched, register pointer is latched
 *           CR2 = SADD|NBYTES=n|RD_WRN|AUTOEND|START  (repeated START)
 *           read RXDR on RXNE, wait STOPF
 *
 * Every wait is bounded, so a missing/stuck device can never hang the firmware.
 */
#include "stm32c0xx.h"
#include "pmu_config.h"
#include "i2c.h"

#define I2Cx             I2C1
/* Bounded spin count for a flag wait. A byte on a 100 kHz bus is ~90 us, so
 * this is generously long, but short enough that scanning 112 addresses
 * cannot stall the boot. */
#define I2C_TIMEOUT      20000u
#define I2C_AF_MAX      16u

/* RM0490, I2C_CR2: "In 7-bit addressing mode (ADD10 = 0): SADD[7:1] must be
 * written with the 7-bit target address to be sent." The address therefore
 * goes into the register pre-shifted, exactly as the byte on the wire. */
#define I2C_SADD(a)      (((uint32_t)(a) << 1) & I2C_CR2_SADD)

static uint32_t s_af = I2C_AF;

/* Local, dependency-free delays: this driver must work even if called before
 * SysTick is running. ~1 us per 12 iterations at 48 MHz is close enough for
 * bus-recovery bit timing and the INA reset pause. */
static void i2c_delay_us(uint32_t us)
{
    for (volatile uint32_t n = us * 12u; n != 0u; n--) {
    }
}

static void i2c_delay_ms(uint32_t ms)
{
    while (ms-- != 0u) {
        i2c_delay_us(1000u);
    }
}

/* ---- GPIO ------------------------------------------------------------- */

static void i2c_gpio_af(uint32_t af)
{
    RCC->IOPENR |= RCC_IOPENR_GPIOBEN;

    /* PB8 = SCL, PB9 = SDA : alternate function, open drain, pull-ups on */
    GPIOB->MODER = (GPIOB->MODER & ~((3u << GPIO_MODER_MODE8_Pos) | (3u << GPIO_MODER_MODE9_Pos))) |
                   (2u << GPIO_MODER_MODE8_Pos) | (2u << GPIO_MODER_MODE9_Pos);
    GPIOB->OTYPER |= (1u << 8) | (1u << 9);
    GPIOB->OSPEEDR |= (3u << GPIO_OSPEEDR_OSPEED8_Pos) | (3u << GPIO_OSPEEDR_OSPEED9_Pos);
    GPIOB->PUPDR = (GPIOB->PUPDR & ~((3u << GPIO_PUPDR_PUPD8_Pos) | (3u << GPIO_PUPDR_PUPD9_Pos))) |
                   (1u << GPIO_PUPDR_PUPD8_Pos) | (1u << GPIO_PUPDR_PUPD9_Pos);

    /* AFR[1] holds pins 8..15: PB8 -> bits 0..3, PB9 -> bits 4..7 */
    GPIOB->AFR[1] = (GPIOB->AFR[1] & ~((0xFu << 0) | (0xFu << 4))) |
                    ((af & 0xFu) << 0) | ((af & 0xFu) << 4);
}

/* Drive the pins as plain GPIO so a wedged bus can be un-wedged. */
static void i2c_gpio_manual(void)
{
    RCC->IOPENR |= RCC_IOPENR_GPIOBEN;
    GPIOB->MODER = (GPIOB->MODER & ~((3u << GPIO_MODER_MODE8_Pos) | (3u << GPIO_MODER_MODE9_Pos))) |
                   (1u << GPIO_MODER_MODE8_Pos) | (1u << GPIO_MODER_MODE9_Pos);
    GPIOB->OTYPER |= (1u << 8) | (1u << 9);   /* open drain */
    GPIOB->BSRR = (1u << 8) | (1u << 9);      /* both released high */
}

static void i2c_periph_init(uint32_t af)
{
    RCC->APBENR1 |= RCC_APBENR1_I2C1EN;

    I2Cx->CR1 = 0u;                       /* disable while reconfiguring */
    I2Cx->TIMINGR = I2C_TIMINGR_VAL;      /* 100 kHz @ 48 MHz kernel clock  */
    I2Cx->CR1 = I2C_CR1_PE;               /* enable, analog filter enabled  */

    i2c_gpio_af(af);
}

void i2c_init_with_af(uint32_t af)
{
    s_af = af;
    i2c_periph_init(af);
}

/* Clock out up to 9 pulses on SCL to free a slave holding SDA low. */
void i2c_bus_recover(void)
{
    I2Cx->CR1 &= ~I2C_CR1_PE;             /* release the pins */
    i2c_gpio_manual();

    for (int i = 0; i < 9; i++) {
        GPIOB->BSRR = (uint32_t)(1u << 8) << 16;   /* SCL low  (BR8) */
        i2c_delay_us(5);
        GPIOB->BSRR = (1u << 8);                   /* SCL high (BS8) */
        i2c_delay_us(5);
    }
    /* STOP: SDA low then high while SCL is high */
    GPIOB->BSRR = (uint32_t)(1u << 9) << 16;
    i2c_delay_us(5);
    GPIOB->BSRR = (1u << 8);
    i2c_delay_us(5);
    GPIOB->BSRR = (1u << 9);
    i2c_delay_us(5);

    i2c_periph_init(s_af);
}

/* ---- low level helpers ------------------------------------------------ */

/* Wait for `flag` in ISR. 0 = ok, -1 = timeout, -2 = NACK from the slave. */
static int wait_isr(uint32_t flag)
{
    for (uint32_t i = 0; i < I2C_TIMEOUT; i++) {
        const uint32_t isr = I2Cx->ISR;

        if (isr & flag) {
            return 0;
        }
        if (isr & I2C_ISR_NACKF) {
            I2Cx->ICR = I2C_ICR_NACKCF | I2C_ICR_STOPCF;
            return -2;
        }
    }
    return -1;
}

static int wait_bus_idle(void)
{
    for (uint32_t i = 0; i < I2C_TIMEOUT; i++) {
        if ((I2Cx->ISR & I2C_ISR_BUSY) == 0u) {
            return 0;
        }
    }
    return -1;
}

/* Clear every sticky flag so a previous (possibly aborted) transfer cannot be
 * mistaken for the result of the next one. START/STOP are the only things the
 * hardware does for us; the flag bits are all software-cleared. */
static void i2c_clear_flags(void)
{
    I2Cx->ICR = I2C_ICR_NACKCF | I2C_ICR_STOPCF | I2C_ICR_BERRCF |
                I2C_ICR_ARLOCF | I2C_ICR_OVRCF | I2C_ICR_PECCF |
                I2C_ICR_TIMOUTCF | I2C_ICR_ALERTCF;
}

/* Toggle PE to abort whatever the peripheral was doing and re-arm the timing.
 * Cheaper than the full bus un-wedge, used on a single failed transaction so
 * one bad transfer cannot poison every following one. */
static void i2c_rearm(void)
{
    I2Cx->CR1 &= ~I2C_CR1_PE;      /* abort any in-flight transfer */
    I2Cx->TIMINGR = I2C_TIMINGR_VAL;
    I2Cx->CR1 = I2C_CR1_PE;
    i2c_clear_flags();
}

static void wait_stop(void)
{
    for (uint32_t i = 0; i < I2C_TIMEOUT; i++) {
        if (I2Cx->ISR & I2C_ISR_STOPF) {
            break;
        }
    }
    I2Cx->ICR = I2C_ICR_STOPCF;
}

/* ---- bus transactions ------------------------------------------------- */

int i2c_write_reg16(uint8_t addr7, uint8_t reg, uint16_t value)
{
    const uint8_t buf[3] = { reg, (uint8_t)(value >> 8), (uint8_t)value };
    int rc;

    if (wait_bus_idle() != 0) {
        i2c_rearm();
        return -1;
    }
    i2c_clear_flags();

    I2Cx->CR2 = I2C_SADD(addr7) |
                (3u << I2C_CR2_NBYTES_Pos) |
                I2C_CR2_AUTOEND | I2C_CR2_START;

    for (uint32_t i = 0; i < 3u; i++) {
        rc = wait_isr(I2C_ISR_TXIS);          /* slave ACKed, TXDR is free */
        if (rc != 0) {
            I2Cx->CR2 |= I2C_CR2_STOP;
            wait_stop();
            i2c_rearm();
            return rc;
        }
        I2Cx->TXDR = buf[i];
    }

    wait_stop();                              /* AUTOEND sends STOP */
    return 0;
}

int i2c_read_reg(uint8_t addr7, uint8_t reg, uint8_t *buf, uint32_t len)
{
    if (len == 0u || len > 255u) {
        return -1;
    }

    if (wait_bus_idle() != 0) {
        i2c_rearm();
        return -1;
    }
    i2c_clear_flags();

    /* --- phase 1: register pointer, no STOP (AUTOEND = 0) --- */
    I2Cx->CR2 = I2C_SADD(addr7) |
                (1u << I2C_CR2_NBYTES_Pos) |
                I2C_CR2_START;

    int rc = wait_isr(I2C_ISR_TXIS);
    if (rc != 0) {
        I2Cx->CR2 |= I2C_CR2_STOP;
        wait_stop();
        i2c_rearm();
        return rc;
    }
    I2Cx->TXDR = reg;

    /* Transfer Complete with AUTOEND=0: bus is held, pointer latched */
    rc = wait_isr(I2C_ISR_TC);
    if (rc != 0) {
        I2Cx->CR2 |= I2C_CR2_STOP;
        wait_stop();
        i2c_rearm();
        return rc;
    }

    /* --- phase 2: repeated START, read len bytes, AUTOEND = 1 --- */
    I2Cx->CR2 = I2C_SADD(addr7) |
                (len << I2C_CR2_NBYTES_Pos) |
                I2C_CR2_RD_WRN | I2C_CR2_AUTOEND | I2C_CR2_START;

    for (uint32_t i = 0; i < len; i++) {
        rc = wait_isr(I2C_ISR_RXNE);
        if (rc != 0) {
            i2c_rearm();
            return rc;
        }
        buf[i] = (uint8_t)I2Cx->RXDR;
    }

    wait_stop();
    return 0;
}

/* Address-only probe: TXIS means the slave ACKed its address.
 *   0 = ACKed, -2 = NACK received, -1 = nothing on the bus / timeout.
 *
 * After a NACK the controller does not raise STOPF (nothing completed), so
 * waiting for it here would burn the full timeout on every empty address -
 * which is what made the 112-address scan take ~4.6 s. */
int i2c_ping(uint8_t addr7)
{
    if (wait_bus_idle() != 0) {
        i2c_rearm();
        return -1;
    }
    i2c_clear_flags();

    I2Cx->CR2 = I2C_SADD(addr7) |
                (1u << I2C_CR2_NBYTES_Pos) |
                I2C_CR2_START;

    const int rc = wait_isr(I2C_ISR_TXIS);

    I2Cx->CR2 |= I2C_CR2_STOP;    /* abort the 1-byte transfer */
    if (rc == 0) {
        wait_stop();              /* ACKed: a real STOP completes */
    } else if (rc == -1) {
        i2c_rearm();              /* no bus activity at all */
    } else {
        i2c_clear_flags();        /* NACK: no STOPF to wait for */
    }

    return rc;
}

