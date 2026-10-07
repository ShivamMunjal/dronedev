#ifndef UART_H
#define UART_H

#include <stdint.h>

/* USART2 (v3 peripheral) on PA2/PA3 = ST-Link Virtual COM Port. */
void uart_init(void);
void uart_putc(char c);
void uart_puts(const char *s);

void uart_print_uint(uint32_t v);
void uart_print_int(int32_t v);
void uart_print_hex8(uint8_t v);
/* Prints `value` with `digits` decimals, sign aware: (23387, 3) -> "23.387" */
void uart_print_fixed(int32_t value, uint32_t digits);
/* Prints an int64 divided by 10^digits with `digits` decimals (no FPU needed) */
void uart_print_fixed64(int64_t value, uint32_t digits);

/* Non-blocking RX: byte, or -1 when nothing waiting. */
int uart_getc(void);

#endif /* UART_H */
