/*
 * uart.c - polling USART2 driver + tiny integer/fixed-point formatter.
 * Deliberately avoids newlib printf: no heap, no syscalls, no float ABI surprises.
 */
#include "stm32f4xx.h"
#include "board.h"
#include "uart.h"

/* APB1 runs at 42 MHz with the 84 MHz clock tree */
#define PCLK1_HZ 42000000u

void uart_init(void)
{
    /* --- clocks --- */
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
    RCC->APB1ENR |= RCC_APB1ENR_USART2EN;

    /* --- PA2 = USART2_TX, PA3 = USART2_RX (AF7) --- */
    GPIOA->MODER = (GPIOA->MODER & ~(GPIO_MODER_MODER2 | GPIO_MODER_MODER3)) |
                   (2u << GPIO_MODER_MODER2_Pos) | (2u << GPIO_MODER_MODER3_Pos);
    GPIOA->OTYPER &= ~(GPIO_OTYPER_OT2 | GPIO_OTYPER_OT3);
    GPIOA->OSPEEDR |= (3u << GPIO_OSPEEDR_OSPEED2_Pos) | (3u << GPIO_OSPEEDR_OSPEED3_Pos);
    /* RX pulled up so an unconnected line idles high */
    GPIOA->PUPDR = (GPIOA->PUPDR & ~(GPIO_PUPDR_PUPDR2 | GPIO_PUPDR_PUPDR3)) |
                   (1u << GPIO_PUPDR_PUPD2_Pos) | (1u << GPIO_PUPDR_PUPD3_Pos);
    GPIOA->AFR[0] = (GPIOA->AFR[0] & ~((0xFu << 8) | (0xFu << 12))) |
                    (7u << 8) | (7u << 12);

    /* --- 115200 8N1 --- */
    USART2->CR1 = 0u;                                   /* disable while config */
    USART2->CR2 = 0u;                                   /* 1 stop bit           */
    USART2->CR3 = 0u;                                   /* no flow control      */
    USART2->BRR = (PCLK1_HZ + (CONSOLE_BAUD / 2u)) / CONSOLE_BAUD;
    USART2->CR1 = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE;
}

int uart_getc(void)
{
    if ((USART2->SR & USART_SR_RXNE) == 0u) {
        return -1;
    }
    return (int)(USART2->DR & 0xFFu);
}

void uart_putc(char c)
{
    while ((USART2->SR & USART_SR_TXE) == 0u) {
    }
    USART2->DR = (uint32_t)(uint8_t)c;
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

void uart_write(const char *buf, uint32_t len)
{
    for (uint32_t i = 0; i < len; i++) {
        uart_putc(buf[i]);
    }
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

void uart_print_float(float value, uint32_t digits)
{
    static const int32_t pow10[] = { 1, 10, 100, 1000, 10000, 100000, 1000000 };
    float scaled;
    int32_t iv;

    if (digits > 6u) {
        digits = 6u;
    }
    scaled = value * (float)pow10[digits];
    iv = (int32_t)(scaled >= 0.0f ? scaled + 0.5f : scaled - 0.5f);
    uart_print_fixed(iv, digits);
}
