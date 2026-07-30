/**
 * EMAX ESC Motor Controller — Bare Metal STM32C092RC
 * No HAL, no BSP, no C library. Raw register access via CMSIS headers.
 * UART control protocol for Ground Station GUI.
 */
#include "stm32c0xx.h"

/* ── State Machine ─────────────────────────────────────────── */
enum { ST_DISARMED = 0, ST_ARMED = 1, ST_KILLED = 2 };
volatile uint32_t motor_state = ST_DISARMED;
volatile uint32_t current_ccr = 1000;
volatile uint32_t last_cmd_tick = 0;
volatile uint32_t sys_tick = 0;

/* ── UART RX buffer ────────────────────────────────────────── */
volatile char rx_buf[32];
volatile uint8_t rx_idx = 0;
volatile uint8_t cmd_ready = 0;

/* ── Minimal string helpers (no libc) ──────────────────────── */
static int my_strlen(const char *s) { int n=0; while(s[n]) n++; return n; }

static void my_itoa(uint32_t val, char *buf) {
    char tmp[12]; int i=0, j=0;
    if (val == 0) { buf[0]='0'; buf[1]=0; return; }
    while (val > 0) { tmp[i++] = '0' + (val % 10); val /= 10; }
    while (i > 0) buf[j++] = tmp[--i];
    buf[j] = 0;
}

static uint32_t my_atoi(const char *s) {
    uint32_t v = 0;
    while (*s >= '0' && *s <= '9') { v = v*10 + (*s - '0'); s++; }
    return v;
}

/* ── UART TX ───────────────────────────────────────────────── */
static void uart_send(const char *s) {
    while (*s) {
        while (!(USART2->ISR & USART_ISR_TXE_TXFNF));  /* wait TXE */
        USART2->TDR = *s++;
    }
}

static void send_event(const char *s) { uart_send(s); uart_send("\r\n"); }

static void send_telemetry(void) {
    char buf[24];
    buf[0] = 'T';
    my_itoa(current_ccr, &buf[1]);
    int len = my_strlen(buf);
    buf[len++] = ',';
    buf[len++] = '0' + motor_state;
    buf[len++] = '\r';
    buf[len++] = '\n';
    buf[len] = 0;
    uart_send(buf);
}

/* ── PWM Control ───────────────────────────────────────────── */
static void set_throttle(uint32_t ccr) {
    if (ccr < 1000) ccr = 1000;
    if (ccr > 2000) ccr = 2000;
    current_ccr = ccr;
    TIM16->CCR1 = ccr;
}

/* ── State Transitions ─────────────────────────────────────── */
static void do_arm(void) {
    if (motor_state == ST_KILLED) return;
    motor_state = ST_ARMED;
    last_cmd_tick = sys_tick;
    set_throttle(1000);
    send_event("ARMED");
}

static void do_disarm(void) {
    motor_state = ST_DISARMED;
    set_throttle(1000);
    send_event("DISARMED");
}

static void do_kill(void) {
    motor_state = ST_KILLED;
    set_throttle(1000);
    TIM16->BDTR &= ~TIM_BDTR_MOE;  /* disable PWM output */
    send_event("KILLED");
}

static void do_reset(void) {
    if (motor_state != ST_KILLED) return;
    TIM16->BDTR |= TIM_BDTR_MOE;   /* re-enable PWM output */
    set_throttle(1000);
    motor_state = ST_DISARMED;
    send_event("DISARMED");
}

/* ── Command Parser ────────────────────────────────────────── */
static void process_cmd(void) {
    char *cmd = (char *)rx_buf;
    /* trim */
    while (*cmd == ' ' || *cmd == '\r' || *cmd == '\n') cmd++;
    if (cmd[0] == 0) return;

    switch (cmd[0]) {
        case 'A': do_arm(); break;
        case 'D': do_disarm(); break;
        case 'S':
            if (motor_state == ST_ARMED) {
                set_throttle(my_atoi(&cmd[1]));
                last_cmd_tick = sys_tick;
            }
            break;
        case 'R': do_reset(); break;
    }
}

/* ── SysTick Handler (1ms) ─────────────────────────────────── */
void SysTick_Handler(void) {
    sys_tick++;
}

/* ── USART2 IRQ Handler ────────────────────────────────────── */
void USART2_IRQHandler(void) {
    if (USART2->ISR & USART_ISR_RXNE_RXFNE) {
        uint8_t b = USART2->RDR;
        if (b == '\n') {
            rx_buf[rx_idx] = 0;
            cmd_ready = 1;
            rx_idx = 0;
        } else {
            if (rx_idx < sizeof(rx_buf) - 1)
                rx_buf[rx_idx++] = b;
            else
                rx_idx = 0;
        }
    }
    USART2->ICR = 0xFFFFFFFF;  /* clear all flags */
}

/* ── EXTI4_15 IRQ Handler (PC13 button) ────────────────────── */
void EXTI4_15_IRQHandler(void) {
    if (EXTI->RPR1 & (1 << 13)) {
        EXTI->RPR1 = (1 << 13);  /* clear pending */
        if (motor_state == ST_KILLED)
            do_reset();
        else
            do_kill();
    }
}

/* ── Hardware Init ─────────────────────────────────────────── */
static void clock_init(void) {
    FLASH->ACR = FLASH_ACR_LATENCY_1;     /* 1WS for 48MHz */
    RCC->CR |= RCC_CR_HSION;
    while (!(RCC->CR & RCC_CR_HSIRDY));
    RCC->CFGR = 0;                         /* HSI as SYSCLK, no dividers */
    SysTick->LOAD = 48000 - 1;             /* 1ms tick */
    SysTick->VAL = 0;
    SysTick->CTRL = SysTick_CTRL_ENABLE_Msk | SysTick_CTRL_CLKSOURCE_Msk | SysTick_CTRL_TICKINT_Msk;
}

static void gpio_init(void) {
    RCC->IOPENR |= RCC_IOPENR_GPIOAEN | RCC_IOPENR_GPIOCEN;

    /* PA2 = USART2_TX (AF1), PA3 = USART2_RX (AF1) */
    GPIOA->MODER &= ~(GPIO_MODER_MODE2 | GPIO_MODER_MODE3);
    GPIOA->MODER |= (2U << GPIO_MODER_MODE2_Pos) | (2U << GPIO_MODER_MODE3_Pos); /* AF */
    GPIOA->AFR[0] &= ~(0xFFU << 8);   /* clear AF for PA2,PA3 */
    GPIOA->AFR[0] |= (1U << 8) | (1U << 12);  /* AF1 for PA2, PA3 */

    /* PA6 = TIM16_CH1 (AF5) */
    GPIOA->MODER &= ~GPIO_MODER_MODE6;
    GPIOA->MODER |= (2U << GPIO_MODER_MODE6_Pos); /* AF */
    GPIOA->AFR[0] &= ~(0xFU << 24);
    GPIOA->AFR[0] |= (5U << 24);  /* AF5 for PA6 */

    /* PA5 = LED Green (output) */
    GPIOA->MODER &= ~GPIO_MODER_MODE5;
    GPIOA->MODER |= (1U << GPIO_MODER_MODE5_Pos); /* output */

    /* PC9 = LED Blue (output) */
    GPIOC->MODER &= ~GPIO_MODER_MODE9;
    GPIOC->MODER |= (1U << GPIO_MODER_MODE9_Pos); /* output */

    /* PC13 = Button (input, pull-up) */
    GPIOC->MODER &= ~GPIO_MODER_MODE13;  /* input */
    GPIOC->PUPDR &= ~GPIO_PUPDR_PUPD13;
    GPIOC->PUPDR |= (1U << GPIO_PUPDR_PUPD13_Pos); /* pull-up */
}

static void tim16_init(void) {
    RCC->APBENR2 |= RCC_APBENR2_TIM16EN;
    TIM16->PSC = 47;        /* 48MHz / 48 = 1MHz tick */
    TIM16->ARR = 19999;     /* 1MHz / 20000 = 50Hz */
    TIM16->CCR1 = 1000;     /* 1ms pulse (minimum throttle) */
    TIM16->CCMR1 = TIM_CCMR1_OC1M_2 | TIM_CCMR1_OC1M_1; /* PWM mode 1 */
    TIM16->CCER = TIM_CCER_CC1E;   /* CH1 output enable */
    TIM16->BDTR = TIM_BDTR_MOE;    /* main output enable */
    TIM16->EGR = TIM_EGR_UG;       /* update generation */
    TIM16->CR1 = TIM_CR1_CEN | TIM_CR1_ARPE; /* start, auto-reload preload */
}

static void usart2_init(void) {
    RCC->APBENR1 |= RCC_APBENR1_USART2EN;
    USART2->BRR = 417;      /* 48MHz / 115200 ≈ 417 */
    USART2->CR1 = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE | USART_CR1_RXNEIE_RXFNEIE;
    NVIC_SetPriority(USART2_IRQn, 1);
    NVIC_EnableIRQ(USART2_IRQn);
}

static void button_init(void) {
    EXTI->EXTICR[3] &= ~EXTI_EXTICR4_EXTI13;  /* PC13 → EXTI13 */
    EXTI->EXTICR[3] |= EXTI_EXTICR4_EXTI13_1;  /* Port C = 0b010 */
    EXTI->RTSR1 |= (1 << 13);   /* rising edge trigger */
    EXTI->IMR1 |= (1 << 13);    /* unmask EXTI13 */
    NVIC_SetPriority(EXTI4_15_IRQn, 2);
    NVIC_EnableIRQ(EXTI4_15_IRQn);
}

/* ── Main ──────────────────────────────────────────────────── */
int main(void) {
    clock_init();
    gpio_init();
    tim16_init();
    usart2_init();
    button_init();

    send_event("DISARMED");

    uint32_t last_telem = 0;

    while (1) {
        /* Process UART command */
        if (cmd_ready) {
            cmd_ready = 0;
            process_cmd();
        }

        /* Watchdog: auto-disarm after 500ms silence while armed */
        if (motor_state == ST_ARMED && (sys_tick - last_cmd_tick) > 500) {
            do_disarm();
            send_event("TIMEOUT");
        }

        /* Telemetry at 10Hz */
        if ((sys_tick - last_telem) >= 100) {
            last_telem = sys_tick;
            send_telemetry();
        }

        /* LED status */
        if (motor_state == ST_ARMED) {
            GPIOA->BSRR = GPIO_BSRR_BS5;   /* green ON */
            GPIOC->BSRR = GPIO_BSRR_BR9;   /* blue OFF */
        } else if (motor_state == ST_KILLED) {
            GPIOA->BSRR = GPIO_BSRR_BR5;   /* green OFF */
            GPIOC->BSRR = GPIO_BSRR_BS9;   /* blue ON */
        } else {
            GPIOA->BSRR = GPIO_BSRR_BR5;   /* both OFF */
            GPIOC->BSRR = GPIO_BSRR_BR9;
        }
    }
}

/* ── Startup & Vector Table ────────────────────────────────── */
extern uint32_t _estack;

void Reset_Handler(void);
void Default_Handler(void) { while(1); }
void NMI_Handler(void)       __attribute__((weak, alias("Default_Handler")));
void HardFault_Handler(void) __attribute__((weak, alias("Default_Handler")));
void SVC_Handler(void)       __attribute__((weak, alias("Default_Handler")));
void PendSV_Handler(void)    __attribute__((weak, alias("Default_Handler")));

__attribute__((section(".isr_vector"), used))
const void *vector_table[] = {
    &_estack,           /* 0: SP */
    Reset_Handler,      /* 1: Reset */
    NMI_Handler,        /* 2: NMI */
    HardFault_Handler,  /* 3: HardFault */
    0, 0, 0, 0, 0, 0, 0,  /* 4-10: Reserved */
    SVC_Handler,        /* 11: SVCall */
    0, 0,               /* 12-13: Reserved */
    PendSV_Handler,     /* 14: PendSV */
    SysTick_Handler,    /* 15: SysTick */
    /* External interrupts (STM32C092) */
    0,                  /* 0: WWDG */
    0,                  /* 1: Reserved */
    0,                  /* 2: RTC */
    0,                  /* 3: FLASH */
    0,                  /* 4: RCC */
    EXTI4_15_IRQHandler, /* 5: EXTI4_15 */
    0,                  /* 6: Reserved */
    0,                  /* 7: Reserved */
    0,                  /* 8: Reserved */
    0,                  /* 9: Reserved */
    0,                  /* 10: Reserved */
    0,                  /* 11: Reserved */
    0,                  /* 12: Reserved */
    USART2_IRQHandler,  /* 13: USART2 */
};

__attribute__((naked, section(".text.Reset_Handler")))
void Reset_Handler(void) {
    __asm volatile(
        ".syntax unified\n\t"
        ".thumb\n\t"
        "ldr r0, =_estack\n\t"
        "mov sp, r0\n\t"
        "bl main\n\t"
        "b .\n\t"
    );
}
