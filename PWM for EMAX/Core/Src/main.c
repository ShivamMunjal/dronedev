/**
 * EMAX ESC Motor Controller — STM32C092RC with LL drivers
 * UART protocol for Ground Station GUI control
 */
#include "main.h"

/* State machine */
enum { ST_DISARMED=0, ST_ARMED=1, ST_KILLED=2 };
volatile uint32_t motor_state = ST_DISARMED;
volatile uint32_t current_ccr = 1000;
volatile uint32_t last_cmd_tick = 0;
volatile uint32_t sys_tick = 0;

/* UART RX */
volatile char rx_buf[32];
volatile uint8_t rx_idx = 0;
volatile uint8_t cmd_ready = 0;

/* Forward declarations */
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART2_UART_Init(void);
static void MX_TIM16_Init(void);
static void uart_send_char(uint8_t c);
static void uart_send_str(const char *s);
static void uart_send_uint(uint32_t v);
static void process_cmd(void);
static void set_throttle(uint32_t v);

int main(void)
{
    LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_SYSCFG);
    LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_PWR);

    SystemClock_Config();
    MX_GPIO_Init();
    MX_TIM16_Init();
    MX_USART2_UART_Init();

    /* Wait for USART2 ready */
    while((!(LL_USART_IsActiveFlag_TEACK(USART2))) || (!(LL_USART_IsActiveFlag_REACK(USART2))));
    LL_USART_EnableIT_RXNE(USART2);

    /* SysTick 1ms */
    SysTick_Config(48000000 / 1000);

    uart_send_str("DISARMED\r\n");

    uint32_t last_telem = 0;

    while (1)
    {
        if (cmd_ready) { cmd_ready = 0; process_cmd(); }

        /* Watchdog */
        if (motor_state == ST_ARMED && (sys_tick - last_cmd_tick) > 500) {
            motor_state = ST_DISARMED;
            set_throttle(1000);
            uart_send_str("TIMEOUT\r\n");
        }

        /* Telemetry 10Hz */
        if ((sys_tick - last_telem) >= 100) {
            last_telem = sys_tick;
            uart_send_char('T');
            uart_send_uint(current_ccr);
            uart_send_char(',');
            uart_send_char('0' + motor_state);
            uart_send_str("\r\n");
        }

        /* LEDs */
        if (motor_state == ST_ARMED) {
            LL_GPIO_SetOutputPin(GPIOA, LL_GPIO_PIN_5);
            LL_GPIO_ResetOutputPin(GPIOC, LL_GPIO_PIN_9);
        } else if (motor_state == ST_KILLED) {
            LL_GPIO_ResetOutputPin(GPIOA, LL_GPIO_PIN_5);
            LL_GPIO_SetOutputPin(GPIOC, LL_GPIO_PIN_9);
        } else {
            LL_GPIO_ResetOutputPin(GPIOA, LL_GPIO_PIN_5);
            LL_GPIO_ResetOutputPin(GPIOC, LL_GPIO_PIN_9);
        }
    }
}

/* ── Clock: HSI 48MHz ── */
void SystemClock_Config(void)
{
    LL_FLASH_SetLatency(LL_FLASH_LATENCY_1);
    LL_RCC_HSI_Enable();
    while(LL_RCC_HSI_IsReady() != 1);
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

/* ── GPIO ── */
static void MX_GPIO_Init(void)
{
    LL_IOP_GRP1_EnableClock(LL_IOP_GRP1_PERIPH_GPIOA);
    LL_IOP_GRP1_EnableClock(LL_IOP_GRP1_PERIPH_GPIOC);

    LL_GPIO_InitTypeDef gpio = {0};

    /* PA5 = LED green output */
    gpio.Pin = LL_GPIO_PIN_5;
    gpio.Mode = LL_GPIO_MODE_OUTPUT;
    gpio.Speed = LL_GPIO_SPEED_FREQ_LOW;
    gpio.OutputType = LL_GPIO_OUTPUT_PUSHPULL;
    gpio.Pull = LL_GPIO_PULL_NO;
    LL_GPIO_Init(GPIOA, &gpio);

    /* PC9 = LED blue output */
    gpio.Pin = LL_GPIO_PIN_9;
    LL_GPIO_Init(GPIOC, &gpio);

    /* PC13 = Button input, pull-up, EXTI falling */
    gpio.Pin = LL_GPIO_PIN_13;
    gpio.Mode = LL_GPIO_MODE_INPUT;
    gpio.Pull = LL_GPIO_PULL_UP;
    LL_GPIO_Init(GPIOC, &gpio);

    LL_EXTI_InitTypeDef exti = {0};
    exti.Line_0_31 = LL_EXTI_LINE_13;
    exti.LineCommand = ENABLE;
    exti.Mode = LL_EXTI_MODE_IT;
    exti.Trigger = LL_EXTI_TRIGGER_FALLING;
    LL_EXTI_Init(&exti);
    LL_EXTI_SetEXTISource(LL_EXTI_CONFIG_PORTC, LL_EXTI_CONFIG_LINE13);

    NVIC_SetPriority(EXTI4_15_IRQn, 3);
    NVIC_EnableIRQ(EXTI4_15_IRQn);
}

/* ── TIM16: 50Hz PWM on PA6 ── */
static void MX_TIM16_Init(void)
{
    LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_TIM16);

    /* PA6 = TIM16_CH1 AF5 */
    LL_GPIO_InitTypeDef gpio = {0};
    gpio.Pin = LL_GPIO_PIN_6;
    gpio.Mode = LL_GPIO_MODE_ALTERNATE;
    gpio.Speed = LL_GPIO_SPEED_FREQ_HIGH;
    gpio.OutputType = LL_GPIO_OUTPUT_PUSHPULL;
    gpio.Pull = LL_GPIO_PULL_NO;
    gpio.Alternate = LL_GPIO_AF_5;
    LL_GPIO_Init(GPIOA, &gpio);

    LL_TIM_SetPrescaler(TIM16, 47);       /* 48MHz/48 = 1MHz */
    LL_TIM_SetAutoReload(TIM16, 19999);   /* 1MHz/20000 = 50Hz */
    LL_TIM_OC_SetCompareCH1(TIM16, 1000); /* 1ms pulse */
    LL_TIM_OC_SetMode(TIM16, LL_TIM_CHANNEL_CH1, LL_TIM_OCMODE_PWM1);
    LL_TIM_OC_SetPolarity(TIM16, LL_TIM_CHANNEL_CH1, LL_TIM_OCPOLARITY_HIGH);
    LL_TIM_CC_EnableChannel(TIM16, LL_TIM_CHANNEL_CH1);
    LL_TIM_EnableAllOutputs(TIM16);
    LL_TIM_EnableCounter(TIM16);
}

/* ── USART2: 115200 8N1 ── */
static void MX_USART2_UART_Init(void)
{
    LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_USART2);

    LL_GPIO_InitTypeDef gpio = {0};
    gpio.Pin = LL_GPIO_PIN_2;
    gpio.Mode = LL_GPIO_MODE_ALTERNATE;
    gpio.Speed = LL_GPIO_SPEED_FREQ_HIGH;
    gpio.OutputType = LL_GPIO_OUTPUT_PUSHPULL;
    gpio.Pull = LL_GPIO_PULL_UP;
    gpio.Alternate = LL_GPIO_AF_1;
    LL_GPIO_Init(GPIOA, &gpio);

    gpio.Pin = LL_GPIO_PIN_3;
    LL_GPIO_Init(GPIOA, &gpio);

    NVIC_SetPriority(USART2_IRQn, 0);
    NVIC_EnableIRQ(USART2_IRQn);

    LL_USART_InitTypeDef usart = {0};
    usart.PrescalerValue = LL_USART_PRESCALER_DIV1;
    usart.BaudRate = 115200;
    usart.DataWidth = LL_USART_DATAWIDTH_8B;
    usart.StopBits = LL_USART_STOPBITS_1;
    usart.Parity = LL_USART_PARITY_NONE;
    usart.TransferDirection = LL_USART_DIRECTION_TX_RX;
    usart.HardwareFlowControl = LL_USART_HWCONTROL_NONE;
    usart.OverSampling = LL_USART_OVERSAMPLING_16;
    LL_USART_Init(USART2, &usart);
    LL_USART_ConfigAsyncMode(USART2);
    LL_USART_Enable(USART2);
}

/* ── UART helpers ── */
static void uart_send_char(uint8_t c)
{
    while(!LL_USART_IsActiveFlag_TXE(USART2));
    LL_USART_TransmitData8(USART2, c);
}

static void uart_send_str(const char *s)
{
    while(*s) uart_send_char(*s++);
}

static void uart_send_uint(uint32_t v)
{
    char buf[12]; int i=0;
    if(v==0){uart_send_char('0');return;}
    while(v>0){buf[i++]='0'+(v%10);v/=10;}
    while(i>0)uart_send_char(buf[--i]);
}

/* ── Throttle ── */
static void set_throttle(uint32_t v)
{
    if(v<1000)v=1000; if(v>2000)v=2000;
    current_ccr=v;
    LL_TIM_OC_SetCompareCH1(TIM16, v);
}

/* ── Command parser ── */
static void process_cmd(void)
{
    char *c = (char*)rx_buf;
    if(c[0]=='A' && motor_state!=ST_KILLED) {
        motor_state=ST_ARMED; last_cmd_tick=sys_tick;
        set_throttle(1000);
        uart_send_str("ARMED\r\n");
    }
    else if(c[0]=='D') {
        motor_state=ST_DISARMED; set_throttle(1000);
        uart_send_str("DISARMED\r\n");
    }
    else if(c[0]=='R' && motor_state==ST_KILLED) {
        LL_TIM_EnableAllOutputs(TIM16);
        motor_state=ST_DISARMED; set_throttle(1000);
        uart_send_str("DISARMED\r\n");
    }
    else if(c[0]=='S' && motor_state==ST_ARMED) {
        uint32_t v=0; char *p=&c[1];
        while(*p>='0'&&*p<='9'){v=v*10+(*p-'0');p++;}
        set_throttle(v); last_cmd_tick=sys_tick;
    }
}

/* ── IRQ Handlers ── */
void SysTick_Handler(void) { sys_tick++; }

void USART2_IRQHandler(void)
{
    if(LL_USART_IsActiveFlag_RXNE(USART2)) {
        uint8_t b = LL_USART_ReceiveData8(USART2);
        if(b=='\n'){rx_buf[rx_idx]=0;cmd_ready=1;rx_idx=0;}
        else if(rx_idx<31) rx_buf[rx_idx++]=b;
    }
    if(LL_USART_IsActiveFlag_ORE(USART2)) LL_USART_ClearFlag_ORE(USART2);
    if(LL_USART_IsActiveFlag_FE(USART2))  LL_USART_ClearFlag_FE(USART2);
}

void EXTI4_15_IRQHandler(void)
{
    if(LL_EXTI_IsActiveRisingFlag_0_31(LL_EXTI_LINE_13)) {
        LL_EXTI_ClearRisingFlag_0_31(LL_EXTI_LINE_13);
        if(motor_state==ST_KILLED) {
            LL_TIM_EnableAllOutputs(TIM16);
            motor_state=ST_DISARMED; set_throttle(1000);
            uart_send_str("DISARMED\r\n");
        } else {
            motor_state=ST_KILLED;
            LL_TIM_DisableAllOutputs(TIM16);
            uart_send_str("KILLED\r\n");
        }
    }
}
