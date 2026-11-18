/* board_n6.c — PWM (TIM1 x4 + TIM14 + TIM16), I2C1, USART1 for NUCLEO-N657X0-Q */
#include "board_n6.h"
#include <string.h>

/* ── timer handles ───────────────────────────────────────────────────────── */
static TIM_HandleTypeDef htim1, htim14, htim16;

/* AF numbers verified in ST's GPIO mode DB for STM32N657 */
const n6_motor_t n6_motors[N6_MOTOR_COUNT] = {
    /* M1 */ { GPIOE, GPIO_PIN_9,  GPIO_AF1_TIM1,  TIM1,  TIM_CHANNEL_1 },
    /* M2 */ { GPIOE, GPIO_PIN_11, GPIO_AF1_TIM1,  TIM1,  TIM_CHANNEL_2 },
    /* M3 */ { GPIOF, GPIO_PIN_6,  GPIO_AF13_TIM1, TIM1,  TIM_CHANNEL_3 },
    /* M4 */ { GPIOC, GPIO_PIN_12, GPIO_AF1_TIM1,  TIM1,  TIM_CHANNEL_4 },
    /* M5 */ { GPIOG, GPIO_PIN_2,  GPIO_AF11_TIM14, TIM14, TIM_CHANNEL_1 },
    /* M6 */ { GPIOA, GPIO_PIN_3,  GPIO_AF1_TIM16,  TIM16, TIM_CHANNEL_1 },
};

/* 500 Hz: timer kernel clock / (PSC+1) / (ARR+1) with 1 MHz tick */
#define PWM_PSC  199u    /* 200 MHz / 200 = 1 MHz            */
#define PWM_ARR  1999u   /* 1 MHz / 2000  = 500 Hz, 1us tick */

static void gpio_af_init(const n6_motor_t *m)
{
    GPIO_InitTypeDef g = {0};
    g.Pin       = m->pin;
    g.Mode      = GPIO_MODE_AF_PP;
    g.Pull      = GPIO_NOPULL;
    g.Speed     = GPIO_SPEED_FREQ_HIGH;
    g.Alternate = m->af;
    HAL_GPIO_Init(m->port, &g);
}

static void tim_base(TIM_HandleTypeDef *h, TIM_TypeDef *inst)
{
    h->Instance               = inst;
    h->Init.Prescaler         = PWM_PSC;
    h->Init.CounterMode       = TIM_COUNTERMODE_UP;
    h->Init.Period            = PWM_ARR;
    h->Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    h->Init.RepetitionCounter = 0;
    h->Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
}

static void pwm_ch(TIM_HandleTypeDef *h, uint32_t ch)
{
    TIM_OC_InitTypeDef oc = {0};
    oc.OCMode       = TIM_OCMODE_PWM1;
    oc.Pulse        = 1000;              /* idle */
    oc.OCPolarity   = TIM_OCPOLARITY_HIGH;
    oc.OCNPolarity  = TIM_OCNPOLARITY_HIGH;
    oc.OCFastMode   = TIM_OCFAST_DISABLE;
    oc.OCIdleState  = TIM_OCIDLESTATE_RESET;
    oc.OCNIdleState = TIM_OCNIDLESTATE_RESET;
    HAL_TIM_PWM_ConfigChannel(h, &oc, ch);
    HAL_TIM_PWM_Start(h, ch);
}

void n6_pwm_init(void)
{
    __HAL_RCC_TIM1_CLK_ENABLE();
    __HAL_RCC_TIM14_CLK_ENABLE();
    __HAL_RCC_TIM16_CLK_ENABLE();
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_GPIOE_CLK_ENABLE();
    __HAL_RCC_GPIOF_CLK_ENABLE();
    __HAL_RCC_GPIOG_CLK_ENABLE();

    for (uint8_t i = 0; i < N6_MOTOR_COUNT; i++) gpio_af_init(&n6_motors[i]);

    /* TIM1 supplies M1..M4 */
    tim_base(&htim1, TIM1);
    if (HAL_TIM_PWM_Init(&htim1) != HAL_OK) return;
    /* HAL channel macros are not contiguous: configure all four explicitly */
    pwm_ch(&htim1, TIM_CHANNEL_1);
    pwm_ch(&htim1, TIM_CHANNEL_2);
    pwm_ch(&htim1, TIM_CHANNEL_3);
    pwm_ch(&htim1, TIM_CHANNEL_4);
    __HAL_TIM_MOE_ENABLE(&htim1);          /* advanced timer: main output enable */

    tim_base(&htim14, TIM14);
    if (HAL_TIM_PWM_Init(&htim14) == HAL_OK) { pwm_ch(&htim14, TIM_CHANNEL_1); }

    tim_base(&htim16, TIM16);
    if (HAL_TIM_PWM_Init(&htim16) == HAL_OK) {
        pwm_ch(&htim16, TIM_CHANNEL_1);
        __HAL_TIM_MOE_ENABLE(&htim16);
    }
}

void n6_pwm_set(uint8_t idx, uint16_t us)
{
    if (idx >= N6_MOTOR_COUNT) return;
    if (us < 1000) us = 1000;
    if (us > 2000) us = 2000;
    const n6_motor_t *m = &n6_motors[idx];
    __HAL_TIM_SET_COMPARE(idx < 4 ? &htim1 : (idx == 4 ? &htim14 : &htim16), m->chan, us);
}

/* ── I2C1 ────────────────────────────────────────────────────────────────── */
I2C_HandleTypeDef n6_hi2c1;

void n6_i2c_init(uint32_t speed_hz)
{
    GPIO_InitTypeDef g = {0};
    __HAL_RCC_I2C1_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_GPIOH_CLK_ENABLE();

    g.Mode      = GPIO_MODE_AF_OD;
    g.Pull      = GPIO_PULLUP;
    g.Speed     = GPIO_SPEED_FREQ_VERY_HIGH;
    g.Alternate = N6_I2C_AF;
    g.Pin       = N6_I2C_SDA_PIN;
    HAL_GPIO_Init(N6_I2C_SDA_PORT, &g);
    g.Pin       = N6_I2C_SCL_PIN;
    HAL_GPIO_Init(N6_I2C_SCL_PORT, &g);

    n6_hi2c1.Instance             = I2C1;
    n6_hi2c1.Init.Timing          = 0x00E0E0E0;  /* 400 kHz-ish, tuned below */
    n6_hi2c1.Init.OwnAddress1     = 0;
    n6_hi2c1.Init.AddressingMode  = I2C_ADDRESSINGMODE_7BIT;
    n6_hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
    n6_hi2c1.Init.OwnAddress2     = 0;
    n6_hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
    n6_hi2c1.Init.NoStretchMode   = I2C_NOSTRETCH_DISABLE;
    HAL_I2C_Init(&n6_hi2c1);

    (void)speed_hz;
}

int n6_i2c_write(uint8_t a, const uint8_t *b, uint16_t n, uint32_t to)
{ return HAL_I2C_Master_Transmit(&n6_hi2c1, (uint16_t)(a << 1), (uint8_t *)b, n, to) == HAL_OK ? 0 : -1; }

int n6_i2c_read(uint8_t a, uint8_t *b, uint16_t n, uint32_t to)
{ return HAL_I2C_Master_Receive(&n6_hi2c1, (uint16_t)(a << 1), b, n, to) == HAL_OK ? 0 : -1; }

int n6_i2c_mem_read(uint8_t a, uint8_t reg, uint8_t *b, uint16_t n)
{ return HAL_I2C_Mem_Read(&n6_hi2c1, (uint16_t)(a << 1), reg, I2C_MEMADD_SIZE_8BIT, b, n, 20) == HAL_OK ? 0 : -1; }

int n6_i2c_mem_write(uint8_t a, uint8_t reg, const uint8_t *b, uint16_t n)
{ return HAL_I2C_Mem_Write(&n6_hi2c1, (uint16_t)(a << 1), reg, I2C_MEMADD_SIZE_8BIT, (uint8_t *)b, n, 20) == HAL_OK ? 0 : -1; }

int n6_i2c_probe(uint8_t a)
{ return HAL_I2C_IsDeviceReady(&n6_hi2c1, (uint16_t)(a << 1), 2, 20) == HAL_OK ? 0 : -1; }

/* ── console ─────────────────────────────────────────────────────────────── */
UART_HandleTypeDef huart1;

void n6_uart_init(void)
{
    GPIO_InitTypeDef g = {0};
    __HAL_RCC_USART1_CLK_ENABLE();
    __HAL_RCC_GPIOE_CLK_ENABLE();
    __HAL_RCC_USART1_CONFIG(RCC_USART1CLKSOURCE_PCLK2);

    g.Pin       = GPIO_PIN_5 | GPIO_PIN_6;      /* PE5 TX / PE6 RX = ST-LINK VCP */
    g.Mode      = GPIO_MODE_AF_PP;
    g.Pull      = GPIO_PULLUP;
    g.Speed     = GPIO_SPEED_FREQ_VERY_HIGH;
    g.Alternate = GPIO_AF7_USART1;
    HAL_GPIO_Init(GPIOE, &g);

    memset(&huart1, 0, sizeof huart1);
    huart1.Instance          = USART1;
    huart1.Init.BaudRate     = 115200;
    huart1.Init.WordLength   = UART_WORDLENGTH_8B;
    huart1.Init.StopBits     = UART_STOPBITS_1;
    huart1.Init.Parity       = UART_PARITY_NONE;
    huart1.Init.Mode         = UART_MODE_TX_RX;
    huart1.Init.HwFlowCtl    = UART_HWCONTROL_NONE;
    huart1.Init.OverSampling = UART_OVERSAMPLING_16;
    HAL_UART_Init(&huart1);
}

void n6_tx(const char *s) { HAL_UART_Transmit(&huart1, (uint8_t *)s, (uint16_t)strlen(s), 100); }
void n6_tx_char(char c)   { HAL_UART_Transmit(&huart1, (uint8_t *)&c, 1, 20); }

void n6_tx_uint(uint32_t v)
{
    char b[11]; int i = 0;
    if (!v) { n6_tx_char('0'); return; }
    while (v) { b[i++] = (char)('0' + (v % 10)); v /= 10; }
    while (i) n6_tx_char(b[--i]);
}

void n6_tx_int(int32_t v)
{
    if (v < 0) { n6_tx_char('-'); n6_tx_uint((uint32_t)(-v)); }
    else n6_tx_uint((uint32_t)v);
}

int n6_rx_char(char *c) { return HAL_UART_Receive(&huart1, (uint8_t *)c, 1, 0) == HAL_OK ? 0 : -1; }
static uint32_t led_state;
void n6_led_set(int pin, int on)
{
    if (pin == 0) { if (on) led_state |= 1u; else led_state &= ~1u; GPIOG->BSRR = on ? (1u<<(0+16)) : (1u<<0); }
}
int n6_led_get(int pin) { (void)pin; return (led_state & 1u) ? 1 : 0; }
