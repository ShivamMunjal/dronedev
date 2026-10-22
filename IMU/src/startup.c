/*
 * startup.c - minimal Cortex-M0+ (ARMv6-M) startup for STM32C092RC.
 * Vector table + .data/.bss init + jump to main().
 *
 * Note: ARMv6-M has no FPU and no configurable vector-table offset, so unlike
 * the Cortex-M4 version there is no CPACR/FPU setup here.
 */
#include <stdint.h>

extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;

int  main(void);
void Reset_Handler(void);
void SysTick_Handler(void);
void HardFault_Handler(void);
void USART2_IRQHandler(void);   /* defined in uart.c (RX ring buffer) */

/* Emergency console: raw USART2 (v3 peripheral) register writes so a fault
 * after uart_init() still produces a message. ISR @0x1C, TDR @0x28. */
static void fault_puts(const char *s)
{
    volatile uint32_t *isr = (volatile uint32_t *)0x4000441Cu;
    volatile uint32_t *tdr = (volatile uint32_t *)0x40004428u;

    while (*s) {
        if (*s == '\n') {
            while ((*isr & 0x80u) == 0u) {   /* TXFNF */
            }
            *tdr = '\r';
        }
        while ((*isr & 0x80u) == 0u) {
        }
        *tdr = (uint32_t)(uint8_t)*s++;
    }
}

void HardFault_Handler(void)
{
    fault_puts("\n!! HARD FAULT (STM32C092RC) - firmware halted !!!\n");
    for (;;) {
    }
}

#define WEAK_HANDLER(name) \
    void name(void) __attribute__((weak, alias("Default_Handler")))

WEAK_HANDLER(NMI_Handler);
WEAK_HANDLER(SVCall_Handler);
WEAK_HANDLER(PendSV_Handler);

void Default_Handler(void)
{
    for (;;) {
    }
}

/* STM32C0 has 32 NVIC interrupts -> 16 core + 32 = 48 vector slots.
 * The ST-LINK debug port is left at its reset alternate function. */
__attribute__((section(".isr_vector"), used))
void (*const g_pfnVectors[])(void) = {
    [0]  = (void (*)(void))&_estack,
    [1]  = Reset_Handler,
    [2]  = NMI_Handler,
    [3]  = HardFault_Handler,
    [11] = SVCall_Handler,
    [14] = PendSV_Handler,
    [15] = SysTick_Handler,   /* defined in system.c */
    [16 ... 43] = Default_Handler,
    [44] = USART2_IRQHandler, /* USART2_IRQn = 28 -> vector 16 + 28 */
    [45 ... 47] = Default_Handler,
};

void Reset_Handler(void)
{
    uint32_t *src = &_sidata;
    uint32_t *dst = &_sdata;
    while (dst < &_edata) {
        *dst++ = *src++;
    }

    for (dst = &_sbss; dst < &_ebss;) {
        *dst++ = 0u;
    }

    main();

    for (;;) {
    }
}
