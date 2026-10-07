#ifndef SYSTEM_H
#define SYSTEM_H

#include <stdint.h>

/* SYSCLK = HSI = 48 MHz (HSIDIV=1), AHB=APB1=48 MHz, 1 flash wait state.
 * This mirrors ST's own SystemClock_Config() for the NUCLEO-C092RC. */
void     system_clock_init(void);

uint32_t system_millis(void);
void     delay_ms(uint32_t ms);
void     delay_us(uint32_t us);

#endif /* SYSTEM_H */
