#ifndef UART_H
#define UART_H

#include <stdint.h>

/* USART2 on PA2/PA3 = ST-Link Virtual COM Port on a Nucleo board. */
void uart_init(void);
void uart_putc(char c);
void uart_puts(const char *s);
void uart_write(const char *buf, uint32_t len);

void uart_print_uint(uint32_t v);
void uart_print_int(int32_t v);
void uart_print_hex8(uint8_t v);
/* Non-blocking RX: returns the byte, or -1 when nothing is waiting. */
int  uart_getc(void);
/* Prints `value` with `digits` decimals, sign aware. e.g. (12345, 2) -> 123.45 */
void uart_print_fixed(int32_t value, uint32_t digits);
/* Rounded variant for floating point accumulators */
void uart_print_float(float value, uint32_t digits);

#endif /* UART_H */
