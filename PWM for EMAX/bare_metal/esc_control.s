.syntax unified
.cpu cortex-m0plus
.thumb

/* ── Register bases ── */
.equ RCC_BASE,      0x40021000
.equ RCC_IOPENR,    0x40021034
.equ RCC_APBENR1,   0x4002103C
.equ RCC_APBENR2,   0x40021040
.equ GPIOA_BASE,    0x50000000
.equ GPIOA_MODER,   0x50000000
.equ GPIOA_BSRR,    0x50000018
.equ GPIOA_AFRL,    0x50000020
.equ GPIOC_BASE,    0x50000008
.equ GPIOC_MODER,   0x50000008
.equ GPIOC_BSRR,    0x50000018
.equ GPIOC_PUPDR,   0x5000000C
.equ TIM16_BASE,    0x40014400
.equ USART2_BASE,   0x40004400
.equ USART2_CR1,    0x40004400
.equ USART2_BRR,    0x4000440C
.equ USART2_ISR,    0x4000441C
.equ USART2_RDR,    0x40004424
.equ USART2_TDR,    0x40004428
.equ USART2_ICR,    0x40004420
.equ EXTI_BASE,     0x40021800
.equ EXTI_IMR1,     0x40021800
.equ EXTI_RTSR1,    0x40021808
.equ EXTI_RPR1,     0x40021810
.equ EXTI_EXTICR4,  0x4002186C
.equ FLASH_ACR,     0x40022000
.equ NVIC_ISER,     0xE000E100
.equ NVIC_IPR,      0xE000E400

/* ── State ── */
.equ ST_DISARMED, 0
.equ ST_ARMED,    1
.equ ST_KILLED,   2

.section .text
.align 2

/* ══════════ VECTOR TABLE ══════════ */
.word 0x20008000          /* SP */
.word _start + 1          /* Reset */
.word 0                   /* NMI */
.word 0                   /* HardFault */
.word 0,0,0,0,0,0,0      /* Reserved */
.word 0                   /* SVCall */
.word 0,0                 /* Reserved */
.word 0                   /* PendSV */
.word SysTick_Handler + 1 /* SysTick */
/* External IRQs */
.word 0                   /* WWDG */
.word 0                   /* Reserved */
.word 0                   /* RTC */
.word 0                   /* FLASH */
.word 0                   /* RCC */
.word EXTI4_15_Handler + 1 /* EXTI4_15 */
.word 0,0,0,0,0,0,0      /* Reserved */
.word USART2_Handler + 1  /* USART2 */

/* ══════════ GLOBALS (in .bss, zeroed at start) ══════════ */
.align 2
state:      .word 0
ccr_val:    .word 1000
last_cmd:   .word 0
tick:       .word 0
rx_buffer:  .space 32
rx_idx:     .word 0
cmd_ready:  .word 0

/* ══════════ STARTUP ══════════ */
.thumb_func
_start:
    ldr r0, =0x20008000
    mov sp, r0
    /* Zero .bss (our globals) */
    ldr r0, =state
    ldr r1, =cmd_ready
    movs r2, #0
1:  str r2, [r0]
    adds r0, #4
    cmp r0, r1
    ble 1b
    /* Init ccr_val to 1000 */
    ldr r0, =ccr_val
    ldr r1, =1000
    str r1, [r0]
    /* Flash latency 1WS */
    ldr r0, =FLASH_ACR
    movs r1, #1
    str r1, [r0]

    bl clock_init
    bl gpio_init
    bl tim16_init
    bl usart2_init
    bl button_init

    /* Send boot message */
    ldr r0, =msg_disarmed
    bl send_str

    /* ══════════ MAIN LOOP ══════════ */
main_loop:
    /* Process command if ready */
    ldr r0, =cmd_ready
    ldr r1, [r0]
    cmp r1, #0
    beq no_cmd
    movs r1, #0
    str r1, [r0]
    bl process_cmd
no_cmd:
    /* Watchdog: auto-disarm after 500ms */
    ldr r0, =state
    ldr r1, [r0]
    cmp r1, #ST_ARMED
    bne no_wd
    ldr r2, =tick
    ldr r2, [r2]
    ldr r3, =last_cmd
    ldr r3, [r3]
    subs r2, r3
    ldr r3, =500
    cmp r2, r3
    blt no_wd
    bl do_disarm
    ldr r0, =msg_timeout
    bl send_str
no_wd:
    /* Telemetry every 100 ticks */
    ldr r0, =tick
    ldr r1, [r0]
    movs r2, #100
    bl tick_mod_check
    cmp r0, #0
    bne no_telem
    bl send_telemetry
no_telem:
    /* LED status */
    ldr r0, =state
    ldr r0, [r0]
    cmp r0, #ST_ARMED
    bne chk_killed
    /* Armed: green ON, blue OFF */
    ldr r0, =GPIOA_BSRR
    movs r1, #0x20       /* PA5 ON */
    str r1, [r0]
    ldr r0, =GPIOC_BSRR
    ldr r1, =0x0200      /* PC9 OFF (BR9) */
    lsls r1, #16
    str r1, [r0]
    b main_loop
chk_killed:
    cmp r0, #ST_KILLED
    bne leds_off
    ldr r0, =GPIOA_BSRR
    movs r1, #0x20
    lsls r1, #16         /* PA5 OFF */
    str r1, [r0]
    ldr r0, =GPIOC_BSRR
    movs r1, #0x02
    lsls r1, #8          /* PC9 ON */
    str r1, [r0]
    b main_loop
leds_off:
    ldr r0, =GPIOA_BSRR
    movs r1, #0x20
    lsls r1, #16
    str r1, [r0]
    ldr r0, =GPIOC_BSRR
    movs r1, #0x02
    lsls r1, #24
    str r1, [r0]
    b main_loop

/* ══════════ INIT FUNCTIONS ══════════ */
.thumb_func
clock_init:
    ldr r0, =RCC_BASE
    ldr r1, [r0]         /* RCC_CR */
    movs r2, #1
    orrs r1, r2          /* HSION */
    str r1, [r0]
    /* SysTick: 48MHz / 48000 = 1ms */
    ldr r0, =0xE000E014  /* SYST_RVR */
    ldr r1, =47999
    str r1, [r0]
    movs r1, #0
    ldr r0, =0xE000E018  /* SYST_CVR */
    str r1, [r0]
    ldr r0, =0xE000E010  /* SYST_CSR */
    movs r1, #7          /* ENABLE | CLKSOURCE | TICKINT */
    str r1, [r0]
    bx lr
    .ltorg
    .ltorg

.thumb_func
gpio_init:
    /* Enable GPIOA + GPIOC clocks */
    ldr r0, =RCC_IOPENR
    ldr r1, [r0]
    movs r2, #5          /* bit0=GPIOA, bit2=GPIOC */
    orrs r1, r2
    str r1, [r0]
    /* PA2=AF (USART2_TX), PA3=AF (USART2_RX) */
    ldr r0, =GPIOA_MODER
    ldr r1, [r0]
    ldr r2, =0xFFFFFCFF  /* clear bits 5:4 and 7:6 */
    ands r1, r2
    ldr r2, =0x000000A0  /* set AF for PA2,PA3 (10 10) */
    orrs r1, r2
    str r1, [r0]
    /* PA2,PA3 AF1 */
    ldr r0, =GPIOA_AFRL
    ldr r1, [r0]
    ldr r2, =0xFFFFF0FF
    ands r1, r2
    ldr r2, =0x00000110  /* AF1 for PA2(bits11:8) and PA3(bits15:12) */
    orrs r1, r2
    str r1, [r0]
    /* PA6=AF (TIM16_CH1, AF5) */
    ldr r0, =GPIOA_MODER
    ldr r1, [r0]
    ldr r2, =0xFFFFCFFF  /* clear bits 13:12 */
    ands r1, r2
    movs r2, #0x08       /* AF mode for PA6 */
    lsls r2, #8
    orrs r1, r2
    str r1, [r0]
    ldr r0, =GPIOA_AFRL
    ldr r1, [r0]
    ldr r2, =0xF0FFFFFF  /* clear bits 27:24 */
    ands r1, r2
    movs r2, #0x05       /* AF5 */
    lsls r2, #24
    orrs r1, r2
    str r1, [r0]
    /* PA5=output (LED green) */
    ldr r0, =GPIOA_MODER
    ldr r1, [r0]
    movs r2, #0x0C
    lsls r2, #8          /* bits 11:10 */
    bics r1, r2
    movs r2, #0x04
    lsls r2, #8
    orrs r1, r2
    str r1, [r0]
    /* PC9=output (LED blue) */
    ldr r0, =GPIOC_MODER
    ldr r1, [r0]
    ldr r2, =0xFFF3FFFF  /* clear bits 19:18 */
    ands r1, r2
    movs r2, #0x01
    lsls r2, #18
    orrs r1, r2
    str r1, [r0]
    /* PC13=input with pull-up (button) */
    ldr r0, =GPIOC_MODER
    ldr r1, [r0]
    ldr r2, =0xF3FFFFFF  /* clear bits 27:26 */
    ands r1, r2
    str r1, [r0]
    ldr r0, =GPIOC_PUPDR
    ldr r1, [r0]
    movs r2, #0x01
    lsls r2, #26         /* pull-up for PC13 */
    orrs r1, r2
    str r1, [r0]
    bx lr
    .ltorg
    .ltorg

.thumb_func
tim16_init:
    ldr r0, =RCC_APBENR2
    ldr r1, [r0]
    ldr r2, =0x2000      /* TIM16EN bit 13 */
    lsls r2, #0
    orrs r1, r2
    str r1, [r0]
    ldr r0, =TIM16_BASE
    movs r1, #47         /* PSC */
    str r1, [r0, #0x28]
    ldr r1, =19999       /* ARR */
    str r1, [r0, #0x2C]
    ldr r1, =1000        /* CCR1 */
    str r1, [r0, #0x34]
    movs r1, #0x60       /* PWM mode 1 (OC1M=110) */
    str r1, [r0, #0x18]  /* CCMR1 */
    movs r1, #1          /* CC1E */
    str r1, [r0, #0x20]  /* CCER */
    movs r1, #0x80       /* MOE */
    lsls r1, #8
    str r1, [r0, #0x44]  /* BDTR */
    movs r1, #1          /* UG */
    str r1, [r0, #0x14]  /* EGR */
    movs r1, #0x81       /* CEN | ARPE */
    str r1, [r0, #0x00]  /* CR1 */
    bx lr
    .ltorg
    .ltorg

.thumb_func
usart2_init:
    ldr r0, =RCC_APBENR1
    ldr r1, [r0]
    ldr r2, =0x20000     /* USART2EN bit 17 */
    orrs r1, r2
    str r1, [r0]
    ldr r0, =USART2_BRR
    ldr r1, =417
    str r1, [r0]
    ldr r0, =USART2_CR1
    movs r1, #0x2D       /* UE|TE|RE|RXNEIE (bits 0,3,2,5) */
    str r1, [r0]
    /* Enable USART2 IRQ (IRQ29 = bit 29 in NVIC_ISER) */
    ldr r0, =NVIC_ISER
    ldr r1, =0x20000000  /* bit 29 */
    str r1, [r0]
    bx lr
    .ltorg
    .ltorg

.thumb_func
button_init:
    /* EXTI13 from port C */
    ldr r0, =EXTI_EXTICR4
    ldr r1, [r0]
    ldr r2, =0xFFFFF8FF  /* clear bits 10:8 */
    ands r1, r2
    movs r2, #0x02       /* port C = 0b010 */
    lsls r2, #8
    orrs r1, r2
    str r1, [r0]
    /* Rising edge trigger */
    ldr r0, =EXTI_RTSR1
    ldr r1, [r0]
    ldr r2, =0x2000      /* bit 13 */
    orrs r1, r2
    str r1, [r0]
    /* Unmask EXTI13 */
    ldr r0, =EXTI_IMR1
    ldr r1, [r0]
    orrs r1, r2
    str r1, [r0]
    /* Enable EXTI4_15 IRQ (IRQ5 = bit 5) */
    ldr r0, =NVIC_ISER
    movs r1, #0x20       /* bit 5 */
    str r1, [r0]
    bx lr
    .ltorg
    .ltorg

/* ══════════ UART FUNCTIONS ══════════ */
.thumb_func
send_char:
    push {r1, lr}
    ldr r1, =USART2_ISR
1:  ldr r0, [r1]
    movs r0, #0x80       /* TXE */
    ldr r0, [r1]
    tst r0, r0
    ldr r0, [r1]
    movs r2, #0x80
    tst r0, r2
    beq 1b
    ldr r1, =USART2_TDR
    str r0, [r1]         /* oops, wrong reg */
    pop {r1, pc}

/* Fixed send_char */
.thumb_func
send_char2:
    push {r1, r2, lr}
    ldr r1, =USART2_ISR
    movs r2, #0x80
1:  ldr r0, [r1]
    tst r0, r2
    beq 1b
    ldr r1, =USART2_TDR
    str r0, [r1]
    pop {r1, r2, pc}

.thumb_func
send_str:
    push {r4, lr}
    mov r4, r0
1:  ldrb r0, [r4]
    cmp r0, #0
    beq 2f
    bl send_char2
    adds r4, #1
    b 1b
2:  /* Send \r\n */
    movs r0, #13
    bl send_char2
    movs r0, #10
    bl send_char2
    pop {r4, pc}

/* ══════════ COMMAND PROCESSING ══════════ */
.thumb_func
process_cmd:
    ldr r0, =rx_buffer
    ldrb r1, [r0]
    cmp r1, #'A'
    beq do_arm
    cmp r1, #'D'
    beq do_disarm
    cmp r1, #'R'
    beq do_reset
    cmp r1, #'S'
    beq parse_throttle
    bx lr
    .ltorg
    .ltorg

.thumb_func
do_arm:
    ldr r0, =state
    ldr r1, [r0]
    cmp r1, #ST_KILLED
    beq 1f
    movs r1, #ST_ARMED
    str r1, [r0]
    /* Update last_cmd */
    ldr r0, =tick
    ldr r1, [r0]
    ldr r0, =last_cmd
    str r1, [r0]
    /* Set throttle to 1000 */
    ldr r0, =ccr_val
    ldr r1, =1000
    str r1, [r0]
    ldr r0, =TIM16_BASE
    str r1, [r0, #0x34]
    ldr r0, =msg_armed
    bl send_str
1:  bx lr

.thumb_func
do_disarm:
    ldr r0, =state
    movs r1, #ST_DISARMED
    str r1, [r0]
    ldr r0, =ccr_val
    ldr r1, =1000
    str r1, [r0]
    ldr r0, =TIM16_BASE
    str r1, [r0, #0x34]
    ldr r0, =msg_disarmed
    bl send_str
    bx lr
    .ltorg
    .ltorg

.thumb_func
do_kill:
    ldr r0, =state
    movs r1, #ST_KILLED
    str r1, [r0]
    ldr r0, =ccr_val
    ldr r1, =1000
    str r1, [r0]
    /* Disable PWM output */
    ldr r0, =TIM16_BASE
    ldr r1, [r0, #0x44]  /* BDTR */
    ldr r2, =0xFFFF7FFF  /* clear MOE */
    ands r1, r2
    str r1, [r0, #0x44]
    ldr r0, =msg_killed
    bl send_str
    bx lr
    .ltorg
    .ltorg

.thumb_func
do_reset:
    ldr r0, =state
    ldr r1, [r0]
    cmp r1, #ST_KILLED
    bne 1f
    /* Re-enable PWM */
    ldr r0, =TIM16_BASE
    ldr r1, [r0, #0x44]
    ldr r2, =0x8000      /* MOE */
    orrs r1, r2
    str r1, [r0, #0x44]
    movs r1, #ST_DISARMED
    ldr r0, =state
    str r1, [r0]
    ldr r0, =msg_disarmed
    bl send_str
1:  bx lr

.thumb_func
parse_throttle:
    ldr r0, =state
    ldr r1, [r0]
    cmp r1, #ST_ARMED
    bne 1f
    /* Parse number after 'S' */
    ldr r0, =rx_buffer
    adds r0, #1          /* skip 'S' */
    movs r1, #0
2:  ldrb r2, [r0]
    cmp r2, #'0'
    blt 3f
    cmp r2, #'9'
    bgt 3f
    subs r2, #'0'
    movs r3, #10
    muls r1, r3
    adds r1, r2
    adds r0, #1
    b 2b
3:  /* Clamp 1000-2000 */
    cmp r1, #232
    bge 4f
    ldr r1, =1000
4:  ldr r2, =2000
    cmp r1, r2
    ble 5f
    mov r1, r2
5:  ldr r0, =ccr_val
    str r1, [r0]
    ldr r0, =TIM16_BASE
    str r1, [r0, #0x34]  /* CCR1 */
    /* Update last_cmd */
    ldr r0, =tick
    ldr r1, [r0]
    ldr r0, =last_cmd
    str r1, [r0]
1:  bx lr

/* ══════════ TELEMETRY ══════════ */
.thumb_func
send_telemetry:
    push {r4, r5, lr}
    /* Send 'T' */
    movs r0, #'T'
    bl send_char2
    /* Send CCR value as decimal */
    ldr r4, =ccr_val
    ldr r4, [r4]
    bl send_uint
    /* Send ',' */
    movs r0, #','
    bl send_char2
    /* Send state */
    ldr r0, =state
    ldr r0, [r0]
    adds r0, #'0'
    bl send_char2
    /* Send \r\n */
    movs r0, #13
    bl send_char2
    movs r0, #10
    bl send_char2
    pop {r4, r5, pc}

.thumb_func
send_uint:
    push {r4, r5, lr}
    mov r4, r0           /* value */
    ldr r5, =num_buf
    movs r0, #0
    str r0, [r5]         /* null terminate */
    /* Build digits in reverse */
    movs r0, #0          /* digit count */
1:  movs r1, #10
    mov r2, r4
    bl uidiv             /* r0 = r4/10, r1 = r4%10 */
    adds r1, #'0'
    str r1, [r5, r0]
    adds r0, #1
    mov r4, r2           /* quotient */
    cmp r4, #0
    bne 1b
    /* Send digits in reverse */
2:  subs r0, #1
    ldrb r0, [r5, r0]
    bl send_char2
    cmp r0, #0
    bne 2b               /* wrong - need to check index not char */
    pop {r4, r5, pc}

/* Simple unsigned divide: r0 = r0/r1, returns quotient in r2, remainder in r1 */
.thumb_func
uidiv:
    mov r2, r0           /* dividend */
    movs r0, #0          /* quotient */
    movs r3, #1          /* bit counter */
    /* Find highest bit */
1:  cmp r2, r1
    blt 2f
    lsls r1, #1
    lsls r3, #1
    b 1b
2:  lsrs r1, #1
    lsrs r3, #1
3:  cmp r3, #0
    beq 4f
    cmp r2, r1
    blt 5f
    subs r2, r1
    adds r0, r3
5:  lsrs r1, #1
    lsrs r3, #1
    b 3b
4:  mov r1, r2           /* remainder */
    mov r2, r0           /* quotient */
    bx lr
    .ltorg
    .ltorg

.thumb_func
tick_mod_check:
    /* r1 = tick value, r2 = modulus. Returns r0=0 if tick%mod==0 */
    mov r0, r1
    bl uidiv
    cmp r1, #0
    beq 1f
    movs r0, #1
    bx lr
    .ltorg
    .ltorg
1:  movs r0, #0
    bx lr
    .ltorg
    .ltorg

/* ══════════ INTERRUPT HANDLERS ══════════ */
.thumb_func
SysTick_Handler:
    ldr r0, =tick
    ldr r1, [r0]
    adds r1, #1
    str r1, [r0]
    bx lr
    .ltorg
    .ltorg

.thumb_func
USART2_Handler:
    ldr r0, =USART2_ISR
    ldr r1, [r0]
    movs r2, #0x20       /* RXNE bit 5 */
    tst r1, r2
    beq 1f
    ldr r0, =USART2_RDR
    ldrb r1, [r0]
    cmp r1, #'\n'
    beq newline
    /* Store byte in buffer */
    ldr r0, =rx_idx
    ldr r2, [r0]
    ldr r0, =rx_buffer
    strb r1, [r0, r2]
    adds r2, #1
    ldr r0, =rx_idx
    cmp r2, #31
    blt 2f
    movs r2, #0
2:  str r2, [r0]
    b 1f
newline:
    /* Null-terminate and set cmd_ready */
    ldr r0, =rx_idx
    ldr r2, [r0]
    ldr r0, =rx_buffer
    movs r1, #0
    strb r1, [r0, r2]
    ldr r0, =cmd_ready
    movs r1, #1
    str r1, [r0]
    ldr r0, =rx_idx
    movs r1, #0
    str r1, [r0]
1:  /* Clear flags */
    ldr r0, =USART2_ICR
    ldr r1, =0xFFFFFFFF
    str r1, [r0]
    bx lr
    .ltorg
    .ltorg

.thumb_func
EXTI4_15_Handler:
    ldr r0, =EXTI_RPR1
    ldr r1, [r0]
    ldr r2, =0x2000      /* bit 13 */
    tst r1, r2
    beq 1f
    str r2, [r0]         /* clear pending */
    ldr r0, =state
    ldr r1, [r0]
    cmp r1, #ST_KILLED
    beq 2f
    bl do_kill
    b 1f
2:  bl do_reset
1:  bx lr

/* ══════════ DATA ══════════ */
.align 2
msg_armed:    .asciz "ARMED"
msg_disarmed: .asciz "DISARMED"
msg_killed:   .asciz "KILLED"
msg_timeout:  .asciz "TIMEOUT"
num_buf:      .space 12
