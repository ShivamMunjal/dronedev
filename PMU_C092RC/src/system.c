/*
 * system.c - clock tree + timebase for STM32C092RC.
 *
 * ST's own template for the NUCLEO-C092RC does not use the PLL at all: the C0
 * HSI runs at 48 MHz and is used directly.
 *   HSI 48 MHz / HSIDIV 1 = 48 MHz -> SYSCLK -> HCLK -> PCLK1 (all prescalers /1)
 *   Flash latency = 1 wait state (required above 24 MHz)
 */
#include "stm32c0xx.h"
#include "system.h"

uint32_t SystemCoreClock = 48000000u;

static volatile uint32_t s_millis;

void SysTick_Handler(void)
{
    s_millis++;
}

void system_clock_init(void)
{
    /* --- HSI on, divider = 1 (this is the reset default, made explicit) --- */
    RCC->CR |= RCC_CR_HSION;
    RCC->CR = (RCC->CR & ~RCC_CR_HSIDIV) | (0u << RCC_CR_HSIDIV_Pos);
    while ((RCC->CR & RCC_CR_HSIRDY) == 0u) {
    }

    /* --- 1 flash wait state + prefetch/caches, exactly as ST does --- */
    FLASH->ACR = (FLASH->ACR & ~FLASH_ACR_LATENCY) | 0x1u;
    FLASH->ACR |= FLASH_ACR_PRFTEN | FLASH_ACR_ICEN;

    /* --- all bus prescalers = 1, SYSCLK source = HSI --- */
    RCC->CFGR = (0u << RCC_CFGR_SW_Pos) |   /* SW  = HSI */
                (0u << 4) |                 /* HPRE  = /1 */
                (0u << 8);                  /* PPRE  = /1 */
    while (((RCC->CFGR & RCC_CFGR_SWS) >> RCC_CFGR_SWS_Pos) != 0u) {
    }

    SystemCoreClock = 48000000u;

    /* --- 1 ms SysTick --- */
    SysTick->LOAD = (SystemCoreClock / 1000u) - 1u;
    SysTick->VAL  = 0u;
    SysTick->CTRL = SysTick_CTRL_CLKSOURCE_Msk | SysTick_CTRL_TICKINT_Msk |
                    SysTick_CTRL_ENABLE_Msk;
}

uint32_t system_millis(void)
{
    return s_millis;
}

void delay_ms(uint32_t ms)
{
    const uint32_t start = s_millis;
    while ((uint32_t)(s_millis - start) < ms) {
    }
}

void delay_us(uint32_t us)
{
    /* 48 cycles per microsecond at 48 MHz */
    const uint32_t loops = us * (SystemCoreClock / 1000000u) / 4u;
    for (volatile uint32_t i = 0; i < loops; i++) {
        __NOP();
    }
}
