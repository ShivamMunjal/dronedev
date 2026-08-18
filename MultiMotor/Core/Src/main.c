/**
 * MultiMotor ESC Controller — 6 independent PWM channels
 * STM32C092RC, NUCLEO-C092RC, LL drivers
 * UART protocol for 6-motor GUI
 */
#include "main.h"

/* ── Motor pin configuration ──────────────────────────────── */
const MotorConfig motors[6] = {
    { TIM16, LL_TIM_CHANNEL_CH1, LL_GPIO_PIN_6,  GPIOA, LL_GPIO_AF_5 },  /* M1: PA6  = TIM16_CH1 (verified: original) */
    { TIM17, LL_TIM_CHANNEL_CH1, LL_GPIO_PIN_7,  GPIOA, LL_GPIO_AF_5 },  /* M2: PA7  = TIM17_CH1 */
    { TIM14, LL_TIM_CHANNEL_CH1, LL_GPIO_PIN_4,  GPIOA, LL_GPIO_AF_4 },  /* M3: PA4  = TIM14_CH1 */
    { TIM1,  LL_TIM_CHANNEL_CH1, LL_GPIO_PIN_8,  GPIOA, LL_GPIO_AF_2 },  /* M4: PA8  = TIM1_CH1 (verified: InputCapture) */
    { TIM1,  LL_TIM_CHANNEL_CH2, LL_GPIO_PIN_1,  GPIOA, LL_GPIO_AF_5 },  /* M5: PA1  = TIM1_CH2 (verified: Central_PWM) */
    { TIM1,  LL_TIM_CHANNEL_CH3, LL_GPIO_PIN_10, GPIOA, LL_GPIO_AF_2 },  /* M6: PA10 = TIM1_CH3 (verified: Central_PWM) */
};

/* ── State ────────────────────────────────────────────────── */
enum { ST_DISARMED=0, ST_ARMED=1, ST_KILLED=2 };
volatile uint32_t motor_state = ST_DISARMED;
volatile uint32_t motor_ccr[6] = {1000,1000,1000,1000,1000,1000};
volatile uint32_t last_cmd_tick = 0;
volatile uint32_t sys_tick = 0;

/* ── UART RX ──────────────────────────────────────────────── */
volatile char rx_buf[32];
volatile uint8_t rx_idx = 0;
volatile uint8_t cmd_ready = 0;

/* Forward declarations */
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART2_UART_Init(void);
static void MX_Timers_Init(void);
static void uart_send_char(uint8_t c);
static void uart_send_str(const char *s);
static void uart_send_uint(uint32_t v);
static void process_cmd(void);

static void set_throttle(uint8_t motor, uint32_t ccr) {
    if (motor >= 6) return;
    if (ccr < 1000) ccr = 1000;
    if (ccr > 2000) ccr = 2000;
    motor_ccr[motor] = ccr;
    const MotorConfig *m = &motors[motor];
    switch (m->channel) {
        case LL_TIM_CHANNEL_CH1: LL_TIM_OC_SetCompareCH1(m->tim, ccr); break;
        case LL_TIM_CHANNEL_CH2: LL_TIM_OC_SetCompareCH2(m->tim, ccr); break;
        case LL_TIM_CHANNEL_CH3: LL_TIM_OC_SetCompareCH3(m->tim, ccr); break;
        case LL_TIM_CHANNEL_CH4: LL_TIM_OC_SetCompareCH4(m->tim, ccr); break;
        default: break;
    }
}

int main(void)
{
    LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_SYSCFG);
    LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_PWR);
    SystemClock_Config();
    MX_GPIO_Init();
    MX_Timers_Init();
    MX_USART2_UART_Init();
    while((!(LL_USART_IsActiveFlag_TEACK(USART2))) || (!(LL_USART_IsActiveFlag_REACK(USART2))));
    LL_USART_EnableIT_RXNE(USART2);

    SysTick_Config(48000000 / 1000);
    uart_send_str("DISARMED\r\n");

    uint32_t last_telem = 0;
    while (1) {
        if (cmd_ready) { cmd_ready = 0; process_cmd(); }

        if (motor_state == ST_ARMED && (sys_tick - last_cmd_tick) > 1000) {
            motor_state = ST_DISARMED;
            for (int i = 0; i < 6; i++) set_throttle(i, 1000);
            uart_send_str("TIMEOUT\r\n");
        }

        if ((sys_tick - last_telem) >= 100) {
            last_telem = sys_tick;
            uart_send_char('T');
            for (int i = 0; i < 6; i++) { uart_send_uint(motor_ccr[i]); uart_send_char(','); }
            uart_send_char('0' + motor_state);
            uart_send_str("\r\n");
        }

        if (motor_state == ST_ARMED) {
            LL_GPIO_SetOutputPin(LED_GREEN_PORT, LED_GREEN_PIN);
            LL_GPIO_ResetOutputPin(LED_BLUE_PORT, LED_BLUE_PIN);
        } else if (motor_state == ST_KILLED) {
            LL_GPIO_ResetOutputPin(LED_GREEN_PORT, LED_GREEN_PIN);
            LL_GPIO_SetOutputPin(LED_BLUE_PORT, LED_BLUE_PIN);
        } else {
            LL_GPIO_ResetOutputPin(LED_GREEN_PORT, LED_GREEN_PIN);
            LL_GPIO_ResetOutputPin(LED_BLUE_PORT, LED_BLUE_PIN);
        }
    }
}

void SystemClock_Config(void) {
    LL_FLASH_SetLatency(LL_FLASH_LATENCY_1);
    LL_RCC_HSI_Enable(); while(LL_RCC_HSI_IsReady() != 1);
    LL_RCC_HSI_SetCalibTrimming(64);
    LL_RCC_SetHSIDiv(LL_RCC_HSI_DIV_1);
    LL_RCC_SetAHBPrescaler(LL_RCC_HCLK_DIV_1);
    LL_RCC_SetSYSDivider(LL_RCC_SYSCLK_DIV_1);
    LL_RCC_SetSysClkSource(LL_RCC_SYS_CLKSOURCE_HSI);
    while(LL_RCC_GetSysClkSource() != LL_RCC_SYS_CLKSOURCE_STATUS_HSI);
    LL_RCC_SetAPB1Prescaler(LL_RCC_APB1_DIV_1);
    LL_Init1msTick(48000000);
    LL_SetSystemCoreClock(48000000);
}

static void MX_GPIO_Init(void) {
    LL_IOP_GRP1_EnableClock(LL_IOP_GRP1_PERIPH_GPIOA);
    LL_IOP_GRP1_EnableClock(LL_IOP_GRP1_PERIPH_GPIOC);

    LL_GPIO_InitTypeDef g = {0};
    g.Pin = LED_GREEN_PIN; g.Mode = LL_GPIO_MODE_OUTPUT; g.Speed = LL_GPIO_SPEED_FREQ_LOW;
    g.OutputType = LL_GPIO_OUTPUT_PUSHPULL; g.Pull = LL_GPIO_PULL_NO;
    LL_GPIO_Init(LED_GREEN_PORT, &g);

    g.Pin = LED_BLUE_PIN;
    LL_GPIO_Init(LED_BLUE_PORT, &g);

    g.Pin = BUTTON_PIN; g.Mode = LL_GPIO_MODE_INPUT; g.Pull = LL_GPIO_PULL_UP;
    LL_GPIO_Init(BUTTON_PORT, &g);

    LL_EXTI_InitTypeDef e = {0};
    e.Line_0_31 = LL_EXTI_LINE_13; e.LineCommand = ENABLE;
    e.Mode = LL_EXTI_MODE_IT; e.Trigger = LL_EXTI_TRIGGER_FALLING;
    LL_EXTI_Init(&e);
    LL_EXTI_SetEXTISource(LL_EXTI_CONFIG_PORTC, LL_EXTI_CONFIG_LINE13);
    NVIC_SetPriority(EXTI4_15_IRQn, 3); NVIC_EnableIRQ(EXTI4_15_IRQn);
}

static void init_one_timer(const MotorConfig *m) {
    if (m->tim == TIM1)  LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_TIM1);
    if (m->tim == TIM2)  LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_TIM2);
    if (m->tim == TIM14) LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_TIM14);
    if (m->tim == TIM16) LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_TIM16);
    if (m->tim == TIM17) LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_TIM17);
}

static void MX_Timers_Init(void) {
    for (uint8_t i = 0; i < 6; i++) {
        const MotorConfig *m = &motors[i];
        init_one_timer(m);

        LL_GPIO_InitTypeDef g = {0};
        g.Pin = m->pin; g.Mode = LL_GPIO_MODE_ALTERNATE;
        g.Speed = LL_GPIO_SPEED_FREQ_HIGH; g.OutputType = LL_GPIO_OUTPUT_PUSHPULL;
        g.Pull = LL_GPIO_PULL_NO; g.Alternate = m->af;
        LL_GPIO_Init(m->port, &g);

        LL_TIM_SetPrescaler(m->tim, 47);
        LL_TIM_SetAutoReload(m->tim, 19999);

        /* Set initial compare value for the correct channel */
        switch (m->channel) {
            case LL_TIM_CHANNEL_CH1: LL_TIM_OC_SetCompareCH1(m->tim, 1000); break;
            case LL_TIM_CHANNEL_CH2: LL_TIM_OC_SetCompareCH2(m->tim, 1000); break;
            case LL_TIM_CHANNEL_CH3: LL_TIM_OC_SetCompareCH3(m->tim, 1000); break;
            case LL_TIM_CHANNEL_CH4: LL_TIM_OC_SetCompareCH4(m->tim, 1000); break;
            default: break;
        }

        LL_TIM_OC_SetMode(m->tim, m->channel, LL_TIM_OCMODE_PWM1);
        LL_TIM_OC_SetPolarity(m->tim, m->channel, LL_TIM_OCPOLARITY_HIGH);
        LL_TIM_CC_EnableChannel(m->tim, m->channel);
        LL_TIM_EnableAllOutputs(m->tim);
        LL_TIM_EnableCounter(m->tim);
    }
}

static void MX_USART2_UART_Init(void) {
    LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_USART2);
    LL_GPIO_InitTypeDef g = {0};
    g.Pin = LL_GPIO_PIN_2|LL_GPIO_PIN_3; g.Mode = LL_GPIO_MODE_ALTERNATE;
    g.Speed = LL_GPIO_SPEED_FREQ_HIGH; g.OutputType = LL_GPIO_OUTPUT_PUSHPULL;
    g.Pull = LL_GPIO_PULL_UP; g.Alternate = LL_GPIO_AF_1;
    LL_GPIO_Init(GPIOA, &g);
    NVIC_SetPriority(USART2_IRQn, 0); NVIC_EnableIRQ(USART2_IRQn);
    LL_USART_InitTypeDef u = {0};
    u.PrescalerValue = LL_USART_PRESCALER_DIV1; u.BaudRate = 115200;
    u.DataWidth = LL_USART_DATAWIDTH_8B; u.StopBits = LL_USART_STOPBITS_1;
    u.Parity = LL_USART_PARITY_NONE; u.TransferDirection = LL_USART_DIRECTION_TX_RX;
    u.HardwareFlowControl = LL_USART_HWCONTROL_NONE; u.OverSampling = LL_USART_OVERSAMPLING_16;
    LL_USART_Init(USART2, &u);
    LL_USART_ConfigAsyncMode(USART2);
    LL_USART_Enable(USART2);
}

/* ── UART helpers ── */
static void uart_send_char(uint8_t c) { while(!LL_USART_IsActiveFlag_TXE(USART2)); LL_USART_TransmitData8(USART2, c); }
static void uart_send_str(const char *s) { while(*s) uart_send_char(*s++); }
static void uart_send_uint(uint32_t v) {
    char b[12]; int i=0;
    if(v==0){uart_send_char('0');return;}
    while(v>0){b[i++]='0'+(v%10);v/=10;}
    while(i>0)uart_send_char(b[--i]);
}

/* ── Command parser ── */
static uint32_t parse_uint(const char *s) {
    uint32_t v = 0;
    while (*s >= '0' && *s <= '9') { v = v*10 + (*s-'0'); s++; }
    return v;
}

static void process_cmd(void) {
    char *c = (char*)rx_buf;

    if (c[0] == 'A') {
        if (motor_state != ST_KILLED) {
            motor_state = ST_ARMED; last_cmd_tick = sys_tick;
            for (int i = 0; i < 6; i++) set_throttle(i, 1000);
            uart_send_str("ARMED\r\n");
        }
    }
    else if (c[0] == 'D') {
        motor_state = ST_DISARMED;
        for (int i = 0; i < 6; i++) set_throttle(i, 1000);
        uart_send_str("DISARMED\r\n");
    }
    else if (c[0] == 'R' && motor_state == ST_KILLED) {
        for (int i = 0; i < 6; i++) {
            LL_TIM_EnableAllOutputs(motors[i].tim);
        }
        motor_state = ST_DISARMED;
        uart_send_str("DISARMED\r\n");
    }
    else if (c[0] == 'S' && motor_state == ST_ARMED) {
        /* Format: S<motor>,<value>  e.g. S1,1500
           Backward compat: S<value> → sets all motors */
        char *p = &c[1];
        uint32_t v1 = parse_uint(p);
        while (*p >= '0' && *p <= '9') p++;
        if (*p == ',') {
            /* S<motor>,<value> — motor is 1-indexed */
            p++;
            uint32_t val = parse_uint(p);
            set_throttle((uint8_t)(v1 - 1), val);  /* convert to 0-index */
        } else {
            /* S<value> — set all motors */
            for (int i = 0; i < 6; i++) set_throttle(i, v1);
        }
        last_cmd_tick = sys_tick;
    }
}

/* ── IRQ Handlers ── */
void SysTick_Handler(void) { sys_tick++; }

void USART2_IRQHandler(void) {
    if (LL_USART_IsActiveFlag_RXNE(USART2)) {
        uint8_t b = LL_USART_ReceiveData8(USART2);
        if (b == '\n') { rx_buf[rx_idx] = 0; cmd_ready = 1; rx_idx = 0; }
        else if (rx_idx < 31) rx_buf[rx_idx++] = b;
    }
    if (LL_USART_IsActiveFlag_ORE(USART2)) LL_USART_ClearFlag_ORE(USART2);
    if (LL_USART_IsActiveFlag_FE(USART2))  LL_USART_ClearFlag_FE(USART2);
}

void EXTI4_15_IRQHandler(void) {
    if (LL_EXTI_IsActiveRisingFlag_0_31(LL_EXTI_LINE_13)) {
        LL_EXTI_ClearRisingFlag_0_31(LL_EXTI_LINE_13);
        if (motor_state == ST_KILLED) {
            for (int i = 0; i < 6; i++) LL_TIM_EnableAllOutputs(motors[i].tim);
            motor_state = ST_DISARMED;
            uart_send_str("DISARMED\r\n");
        } else {
            motor_state = ST_KILLED;
            for (int i = 0; i < 6; i++) LL_TIM_DisableAllOutputs(motors[i].tim);
            uart_send_str("KILLED\r\n");
        }
    }
}
