#ifndef SYSTEM_H
#define SYSTEM_H

#include <stdint.h>

/* Brings SYSCLK to 84 MHz (HSI 16 MHz -> PLL) and starts the 1 ms SysTick. */
void     system_clock_init(void);

/* Milliseconds since boot (1 ms SysTick). */
uint32_t system_millis(void);

void     delay_ms(uint32_t ms);
void     delay_us(uint32_t us);

#endif /* SYSTEM_H */
