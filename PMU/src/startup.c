/*
 * startup.c - minimal Cortex-M4 startup for STM32F401RE.
 * Vector table + .data/.bss init + jump to main().
 */
#include <stdint.h>

/* Provided by the linker script */
extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;

int  main(void);
void Reset_Handler(void);
void SysTick_Handler(void);
void HardFault_Handler(void);

/* Emergency console: raw USART2 register writes. Works even before/without the
 * uart driver, as long as USART2 has been configured. */
static void fault_puts(const char *s)
{
    volatile uint32_t *sr = (volatile uint32_t *)0x40004400u;
    volatile uint32_t *dr = (volatile uint32_t *)0x40004404u;

    while (*s) {
        if (*s == '\n') {
            while ((*sr & 0x80u) == 0u) {
            }
            *dr = '\r';
        }
        while ((*sr & 0x80u) == 0u) {
        }
        *dr = (uint32_t)(uint8_t)*s++;
    }
}

void HardFault_Handler(void)
{
    fault_puts("\n!! HARD FAULT - firmware halted !!!\n");
    for (;;) {
    }
}

/* ---- Default handlers (weak, can be overridden) ---- */
#define WEAK_HANDLER(name)              \
    void name(void) __attribute__((weak, alias("Default_Handler")))

WEAK_HANDLER(NMI_Handler);
WEAK_HANDLER(MemManage_Handler);
WEAK_HANDLER(BusFault_Handler);
WEAK_HANDLER(UsageFault_Handler);
WEAK_HANDLER(SVCall_Handler);
WEAK_HANDLER(DebugMon_Handler);
WEAK_HANDLER(PendSV_Handler);

void Default_Handler(void)
{
    for (;;) {
    }
}

/* ---- Vector table ---- */
__attribute__((section(".isr_vector"), used))
void (*const g_pfnVectors[])(void) = {
    [0]  = (void (*)(void))&_estack,   /* initial stack pointer  */
    [1]  = Reset_Handler,
    [2]  = NMI_Handler,
    [3]  = HardFault_Handler,
    [4]  = MemManage_Handler,
    [5]  = BusFault_Handler,
    [6]  = UsageFault_Handler,
    [11] = SVCall_Handler,
    [12] = DebugMon_Handler,
    [14] = PendSV_Handler,
    [15] = SysTick_Handler,   /* defined in system.c */
    [16 ... 100] = Default_Handler,
};

/* ---- Reset handler ---- */
void Reset_Handler(void)
{
    /* Enable the FPU (CP10/CP11 full access) *before* any C code runs: GCC
     * emits VFP register saves in the prologue of functions that use floats,
     * which would otherwise raise a NOCP UsageFault on the very first call. */
    *(volatile uint32_t *)0xE000ED88u |= (0xFu << 20);
    __asm volatile("dsb");
    __asm volatile("isb");

    /* copy .data from flash to SRAM */
    uint32_t *src = &_sidata;
    uint32_t *dst = &_sdata;
    while (dst < &_edata) {
        *dst++ = *src++;
    }

    /* zero .bss */
    for (dst = &_sbss; dst < &_ebss;) {
        *dst++ = 0u;
    }

    main();

    for (;;) {
    }
}
