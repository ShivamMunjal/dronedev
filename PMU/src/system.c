/*
 * system.c - clock tree + timebase for STM32F401RE.
 *
 * Target: SYSCLK 84 MHz from the internal 16 MHz HSI (no external crystal
 * required on a Nucleo-64 board):
 *   HSI 16 MHz / PLLM 16 = 1 MHz  -> x PLLN 336 = 336 MHz -> / PLLP 4 = 84 MHz
 *   AHB  = 84 MHz, APB1 = 42 MHz, APB2 = 84 MHz, flash latency = 2 WS
 */
#include "stm32f4xx.h"
#include "system.h"

uint32_t SystemCoreClock = 84000000u;

static volatile uint32_t s_millis;

void SysTick_Handler(void)
{
    s_millis++;
}

void system_clock_init(void)
{
    /* --- Regulator voltage scaling: Scale 2 is the CubeMX default for 84 MHz --- */
    RCC->APB1ENR |= RCC_APB1ENR_PWREN;
    (void)RCC->APB1ENR;
    PWR->CR = (PWR->CR & ~PWR_CR_VOS) | PWR_CR_VOS_1;
    for (volatile int i = 0; i < 1000; i++) {
        __NOP();
    }

    /* --- HSI on --- */
    RCC->CR |= RCC_CR_HSION;
    while ((RCC->CR & RCC_CR_HSIRDY) == 0u) {
    }

    /* --- Flash: prefetch + caches + 2 wait states (needed above 60 MHz) --- */
    FLASH->ACR = FLASH_ACR_PRFTEN | FLASH_ACR_ICEN | FLASH_ACR_DCEN |
                 FLASH_ACR_LATENCY_2WS;

    /* --- Bus prescalers (write before switching the PLL in) --- */
    RCC->CFGR = RCC_CFGR_HPRE_DIV1 | RCC_CFGR_PPRE1_DIV2 | RCC_CFGR_PPRE2_DIV1;

    /* --- PLL: HSI source, M=16, N=336, P=4, Q=7 --- */
    RCC->PLLCFGR = (16u << RCC_PLLCFGR_PLLM_Pos) |
                   (336u << RCC_PLLCFGR_PLLN_Pos) |
                   (1u << RCC_PLLCFGR_PLLP_Pos) |   /* 0b01 -> P = 4      */
                   (7u << RCC_PLLCFGR_PLLQ_Pos) |
                   (0u << RCC_PLLCFGR_PLLSRC_Pos);  /* 0 = HSI            */

    RCC->CR |= RCC_CR_PLLON;
    while ((RCC->CR & RCC_CR_PLLRDY) == 0u) {
    }

    /* --- Switch SYSCLK to PLL --- */
    RCC->CFGR = (RCC->CFGR & ~RCC_CFGR_SW) | RCC_CFGR_SW_PLL;
    while (((RCC->CFGR & RCC_CFGR_SWS) >> RCC_CFGR_SWS_Pos) != 2u) {
    }

    SystemCoreClock = 84000000u;

    /* --- 1 ms SysTick on the processor clock --- */
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
    /* 84 cycles per microsecond at 84 MHz; crude but adequate for bit delays */
    const uint32_t loops = us * (SystemCoreClock / 1000000u) / 4u;
    for (volatile uint32_t i = 0; i < loops; i++) {
        __NOP();
    }
}
