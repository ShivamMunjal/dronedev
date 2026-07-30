#include <stdint.h>
#define R(a) (*(volatile uint32_t*)(a))

void SystemInit(void) {}  /* Called by startup, minimal */

static void sc(uint8_t c) { while(!(R(0x4000441C)&0x80)); R(0x40004428)=c; }
static void ss(const char*s) { while(*s) sc(*s++); }

static void send_uint(uint32_t v) {
    char buf[12]; int i=0;
    if(v==0){sc('0');return;}
    while(v>0){buf[i++]='0'+(v%10);v/=10;}
    while(i>0)sc(buf[--i]);
}

/* State */
static volatile uint32_t state=0, ccr=1000, last_cmd=0, tick=0;
static volatile char rxb[32]; static volatile uint8_t rxi=0, cmd_rdy=0;

void USART2_IRQHandler(void) {
    if(R(0x4000441C)&0x20) {
        uint8_t b=R(0x40004424);
        if(b=='\n'){rxb[rxi]=0;cmd_rdy=1;rxi=0;}
        else if(rxi<31)rxb[rxi++]=b;
    }
    R(0x40004420)=0xFFFFFFFF;
}

void SysTick_Handler(void) { tick++; }

void EXTI4_15_IRQHandler(void) {
    if(R(0x40021810)&0x2000) {
        R(0x40021810)=0x2000;
        if(state==2){R(0x40014444)|=0x8000;state=0;ss("DISARMED\r\n");}
        else{state=2;R(0x40014444)&=~0x8000;ss("KILLED\r\n");}
    }
}

static void set_thr(uint32_t v){if(v<1000)v=1000;if(v>2000)v=2000;ccr=v;R(0x40014434)=v;}

static void process(void) {
    char*c=(char*)rxb;
    if(c[0]=='A'&&state!=2){state=1;last_cmd=tick;set_thr(1000);ss("ARMED\r\n");}
    else if(c[0]=='D'){state=0;set_thr(1000);ss("DISARMED\r\n");}
    else if(c[0]=='R'&&state==2){R(0x40014444)|=0x8000;state=0;ss("DISARMED\r\n");}
    else if(c[0]=='S'&&state==1){
        uint32_t v=0;char*p=&c[1];
        while(*p>='0'&&*p<='9'){v=v*10+(*p-'0');p++;}
        set_thr(v);last_cmd=tick;
    }
}

int main(void) {
    /* Flash 1WS for 48MHz */
    R(0x40022000)=1;
    /* GPIOA+GPIOC clocks */
    R(0x40021034)|=0x5;
    /* PA2,PA3 = AF1 (USART2) — clear bits 7:4, set 1010 */
    R(0x50000000)=(R(0x50000000)&0xFFFFFF0F)|0xA0;
    R(0x50000020)=(R(0x50000020)&0xFFFFF0FF)|0x110; /* AF1 for PA2+PA3 */
    /* PA6 = AF5 (TIM16_CH1) */
    R(0x50000000)=(R(0x50000000)&0xFFFFCFFF)|0x8000;
    R(0x50000020)=(R(0x50000020)&0xF0FFFFFF)|0x5000000;
    /* PA5 = output (LED) */
    R(0x50000000)=(R(0x50000000)&0xFFFFF3FF)|0x400;
    /* PC9 = output (LED) */
    R(0x50000800)=(R(0x50000800)&0xFFF3FFFF)|0x40000;
    /* PC13 = input pull-up (button) */
    R(0x50000800)&=0xF3FFFFFF;
    R(0x5000080C)=(R(0x5000080C)&0xF3FFFFFF)|0x4000000;

    /* TIM16: 50Hz PWM */
    R(0x40021040)|=0x2000;
    R(0x40014428)=47;       /* PSC */
    R(0x4001442C)=19999;    /* ARR */
    R(0x40014434)=1000;     /* CCR1 */
    R(0x40014418)=0x60;     /* CCMR1: PWM mode 1 */
    R(0x40014420)=1;        /* CCER: CC1E */
    R(0x40014444)=0x8000;   /* BDTR: MOE */
    R(0x40014414)=1;        /* EGR: UG */
    R(0x40014400)=0x81;     /* CR1: CEN|ARPE */

    /* USART2: 115200 */
    R(0x4002103C)|=0x20000;
    R(0x4000440C)=417;
    R(0x40004400)=0x2D;     /* UE|TE|RE|RXNEIE */
    R(0xE000E100)=0x20000000; /* NVIC: USART2 IRQ29 */

    /* Button EXTI13 */
    R(0x4002186C)=(R(0x4002186C)&0xFFFFF8FF)|0x200; /* PC13 */
    R(0x40021808)|=0x2000;  /* rising edge */
    R(0x40021800)|=0x2000;  /* unmask */
    R(0xE000E100)|=0x20;    /* NVIC: EXTI4_15 IRQ5 */

    /* SysTick 1ms */
    R(0xE000E014)=47999;
    R(0xE000E018)=0;
    R(0xE000E010)=7;

    ss("DISARMED\r\n");
    uint32_t lt=0;
    while(1) {
        if(cmd_rdy){cmd_rdy=0;process();}
        if(state==1&&(tick-last_cmd)>500){state=0;set_thr(1000);ss("TIMEOUT\r\n");}
        if((tick-lt)>=100){lt=tick;sc('T');send_uint(ccr);sc(',');sc('0'+state);ss("\r\n");}
        /* LEDs */
        if(state==1){R(0x50000018)=0x20;R(0x50000818)=0x200<<16;}
        else if(state==2){R(0x50000018)=0x20<<16;R(0x50000818)=0x200;}
        else{R(0x50000018)=0x20<<16;R(0x50000818)=0x200<<16;}
    }
}
void __libc_init_array(void) {}
