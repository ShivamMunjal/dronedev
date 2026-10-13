/*
 * uart.c - polling USART2 driver (STM32C0 "USART v3" peripheral) plus a tiny
 * integer/fixed-point formatter.
 *
 * v3 differences vs the F4 USART: flags live in ISR (not SR), data goes through
 * TDR/RDR (not DR). TXFNF/RXFNE are the FIFO-not-full / not-empty flags, which
 * are what TXE/RXNE collapse to when the FIFO is disabled.
 *
 * Deliberately uses no floating point: the Cortex-M0+ has no FPU, so floats
 * would drag in libgcc soft-float routines.
 */
#include "stm32c0xx.h"
#include "board.h"
#include "uart.h"

void uart_init(void)
{
    /* --- clocks --- */
    RCC->IOPENR |= RCC_IOPENR_GPIOAEN;
    RCC->APBENR1 |= RCC_APBENR1_USART2EN;

    /* --- PA2 = USART2_TX, PA3 = USART2_RX (AF1) --- */
    GPIOA->MODER = (GPIOA->MODER & ~((3u << GPIO_MODER_MODE2_Pos) | (3u << GPIO_MODER_MODE3_Pos))) |
                   (2u << GPIO_MODER_MODE2_Pos) | (2u << GPIO_MODER_MODE3_Pos);
    GPIOA->OTYPER &= ~((1u << 2) | (1u << 3));
    GPIOA->OSPEEDR |= (3u << GPIO_OSPEEDR_OSPEED2_Pos) | (3u << GPIO_OSPEEDR_OSPEED3_Pos);
    GPIOA->PUPDR = (GPIOA->PUPDR & ~((3u << GPIO_PUPDR_PUPD2_Pos) | (3u << GPIO_PUPDR_PUPD3_Pos))) |
                   (1u << GPIO_PUPDR_PUPD2_Pos) | (1u << GPIO_PUPDR_PUPD3_Pos);
    GPIOA->AFR[0] = (GPIOA->AFR[0] & ~((0xFu << 8) | (0xFu << 12))) |
                    (UART_AF << 8) | (UART_AF << 12);

    /* --- 115200 8N1, prescaler = 1 --- */
    USART2->CR1 = 0u;                                  /* disable while configuring */
    USART2->CR2 = 0u;                                  /* 1 stop bit */
    USART2->CR3 = 0u;                                  /* no flow control */
    USART2->PRESC = 0u;                                /* no prescaler division */
    USART2->BRR = (PCLK1_HZ + (CONSOLE_BAUD / 2u)) / CONSOLE_BAUD;
    USART2->CR1 = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE;
}

void uart_putc(char c)
{
    while ((USART2->ISR & USART_ISR_TXE_TXFNF) == 0u) {   /* TX register free */
    }
    USART2->TDR = (uint32_t)(uint8_t)c;
}

void uart_puts(const char *s)
{
    while (*s) {
        if (*s == '\n') {
            uart_putc('\r');
        }
        uart_putc(*s++);
    }
}

int uart_getc(void)
{
    const uint32_t isr = USART2->ISR;

    /* A latched error stops RX from progressing and swallows every following
     * character. That happens routinely here: the 100 Hz stream keeps the CPU
     * busy enough that a typed command is overrun. Clearing it requires reading
     * ISR (done above, into isr) and then DR - which is why RDR is read here.
     * Without this, 'x' and '?' were silently eaten while streaming. */
    if (isr & (USART_ISR_ORE | USART_ISR_FE | USART_ISR_NE | USART_ISR_PE)) {
        (void)USART2->RDR;
        return -1;
    }
    if ((isr & USART_ISR_RXNE_RXFNE) == 0u) {
        return -1;
    }
    return (int)(USART2->RDR & 0xFFu);
}

void uart_print_uint(uint32_t v)
{
    char tmp[10];
    uint32_t n = 0;

    if (v == 0u) {
        uart_putc('0');
        return;
    }
    while (v > 0u) {
        tmp[n++] = (char)('0' + (v % 10u));
        v /= 10u;
    }
    while (n > 0u) {
        uart_putc(tmp[--n]);
    }
}

void uart_print_int(int32_t v)
{
    if (v < 0) {
        uart_putc('-');
        uart_print_uint((uint32_t)(-(int64_t)v));
    } else {
        uart_print_uint((uint32_t)v);
    }
}

void uart_print_hex8(uint8_t v)
{
    static const char hex[] = "0123456789ABCDEF";
    uart_putc(hex[(v >> 4) & 0xFu]);
    uart_putc(hex[v & 0xFu]);
}

void uart_print_fixed(int32_t value, uint32_t digits)
{
    static const int32_t pow10[] = { 1, 10, 100, 1000, 10000, 100000, 1000000 };
    int32_t scale;
    int32_t iv;
    int neg = 0;

    if (digits > 6u) {
        digits = 6u;
    }
    scale = pow10[digits];

    if (value < 0) {
        neg = 1;
        value = -value;
    }

    iv = value / scale;
    if (neg) {
        uart_putc('-');
    }
    uart_print_uint((uint32_t)iv);

    if (digits > 0u) {
        int32_t frac = value % scale;
        uart_putc('.');
        for (int32_t d = scale / 10; d > 0; d /= 10) {
            if (frac < d) {
                uart_putc('0');
            }
        }
        uart_print_uint((uint32_t)frac);
    }
}

/* Prints value / 10^digits with `digits` decimals. Used for the mAh / Wh
 * accumulators, which are held as 64-bit integer sums instead of floats. */
void uart_print_fixed64(int64_t value, uint32_t digits)
{
    static const int64_t pow10[] = { 1, 10, 100, 1000, 10000, 100000, 1000000,
                                     10000000, 100000000, 1000000000 };
    int neg = 0;

    if (digits > 9u) {
        digits = 9u;
    }
    if (value < 0) {
        neg = 1;
        value = -value;
    }
    if (neg) {
        uart_putc('-');
    }

    const int64_t scale = pow10[digits];
    uart_print_uint((uint32_t)(value / scale));

    if (digits > 0u) {
        int64_t frac = value % scale;
        uart_putc('.');
        for (int64_t d = scale / 10; d > 0; d /= 10) {
            if (frac < d) {
                uart_putc('0');
            }
        }
        uart_print_uint((uint32_t)frac);
    }
}
