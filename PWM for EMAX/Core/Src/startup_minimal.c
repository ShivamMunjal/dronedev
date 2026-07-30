#include <stdint.h>

extern int main(void);
extern uint32_t _estack;

void Reset_Handler(void) __attribute__((naked, section(".text.Reset_Handler")));
void Reset_Handler(void)
{
    __asm volatile(
        ".syntax unified\n\t"
        ".thumb\n\t"
        /* Set SP */
        "ldr r0, =_estack\n\t"
        "mov sp, r0\n\t"
        /* Flash latency = 1WS for 48MHz */
        "ldr r0, =0x40022000\n\t"
        "movs r1, #1\n\t"
        "str r1, [r0]\n\t"
        /* Copy .data */
        "ldr r0, =_sidata\n\t"
        "ldr r1, =_sdata\n\t"
        "ldr r2, =_edata\n\t"
        "b 2f\n\t"
        "1:\n\t"
        "ldm r0!, {r3}\n\t"
        "stm r1!, {r3}\n\t"
        "2:\n\t"
        "cmp r1, r2\n\t"
        "bcc 1b\n\t"
        /* Zero .bss */
        "ldr r0, =_sbss\n\t"
        "ldr r2, =_ebss\n\t"
        "movs r1, #0\n\t"
        "b 4f\n\t"
        "3:\n\t"
        "stm r0!, {r1}\n\t"
        "4:\n\t"
        "cmp r0, r2\n\t"
        "bcc 3b\n\t"
        /* Call main */
        "bl main\n\t"
        "b .\n\t"
    );
}

extern void Reset_Handler(void);
extern void HardFault_Handler(void);
void Default_Handler(void) { while(1); }
void NMI_Handler(void)       __attribute__((weak, alias("Default_Handler")));
void SVC_Handler(void)       __attribute__((weak, alias("Default_Handler")));
void PendSV_Handler(void)    __attribute__((weak, alias("Default_Handler")));
void SysTick_Handler(void)   __attribute__((weak, alias("Default_Handler")));

__attribute__((section(".isr_vector"), used))
const uint32_t g_pfnVectors[] = {
    (uint32_t)&_estack,
    (uint32_t)&Reset_Handler,
    (uint32_t)&NMI_Handler,
    (uint32_t)&HardFault_Handler,
    0, 0, 0, 0, 0, 0, 0,
    (uint32_t)&SVC_Handler,
    0, 0,
    (uint32_t)&PendSV_Handler,
    (uint32_t)&SysTick_Handler,
};
