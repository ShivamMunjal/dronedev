/**
 * MultiMotor ESC Controller — 6 independent PWM channels
 * STM32C092RC, NUCLEO-C092RC, LL drivers
 * UART protocol for 6-motor GUI
 */
#include "main.h"
#include "mixer.h"
#include "pmu.h"
#include "i2c.h"
#include "ism330is.h"
#include "fusion.h"

/* ── Motor pin configuration ──────────────────────────────── */
const MotorConfig motors[6] = {
    { TIM16, LL_TIM_CHANNEL_CH1, LL_GPIO_PIN_6,  GPIOA, LL_GPIO_AF_5 },  /* M1: PA6  = TIM16_CH1 (verified: original) */
    { TIM17, LL_TIM_CHANNEL_CH1, LL_GPIO_PIN_7,  GPIOA, LL_GPIO_AF_5 },  /* M2: PA7  = TIM17_CH1 */
    { TIM14, LL_TIM_CHANNEL_CH1, LL_GPIO_PIN_4,  GPIOA, LL_GPIO_AF_4 },  /* M3: PA4  = TIM14_CH1 */
    { TIM1,  LL_TIM_CHANNEL_CH1, LL_GPIO_PIN_8,  GPIOA, LL_GPIO_AF_2 },  /* M4: PA8  = TIM1_CH1 (verified: InputCapture) */
    { TIM1,  LL_TIM_CHANNEL_CH2, LL_GPIO_PIN_1,  GPIOA, LL_GPIO_AF_5 },  /* M5: PA1  = TIM1_CH2 (verified: Central_PWM) */
    { TIM1,  LL_TIM_CHANNEL_CH3, LL_GPIO_PIN_10, GPIOA, LL_GPIO_AF_2 },  /* M6: PA10 = TIM1_CH3 (verified: Central_PWM) */
};

/* ── State ────────────────────────────────────────────────── */
enum { ST_DISARMED=0, ST_ARMED=1, ST_KILLED=2 };
volatile uint32_t motor_state = ST_DISARMED;
volatile uint32_t motor_ccr[6] = {1000,1000,1000,1000,1000,1000};       /* actual PWM (ramped) */
volatile uint32_t motor_target[6] = {1000,1000,1000,1000,1000,1000};    /* commanded target */
volatile uint32_t last_cmd_tick = 0;
volatile uint32_t sys_tick = 0;

/* Commanded mixer inputs: throttle in microseconds (1000 = zero thrust), and
 * roll/pitch/yaw in microseconds of authority. The firmware owns this state so
 * an emergency stop can genuinely clear it — otherwise a later arm would
 * resume from whatever the GUI last sent. */
volatile int32_t mix_in[4] = { MIXER_MIN_US, 0, 0, 0 };   /* thr, roll, pitch, yaw */

/* Deferred event reporting. Safety actions happen immediately in the button
 * ISR, but the UART messages are emitted from the main loop: writing from the
 * ISR could splice a line into the middle of the telemetry stream. */
volatile uint8_t kill_event = 0;    /* 0 none, 1 killed, 2 recovered */

/* ── IMU (ISM330IS on I2C2 PB10/PB11 + ST MotionFX 6X) ─────────────────── */
static int      imu_ok        = 0;
static int      imu_stream    = 1;           /* emit E, lines */
static int32_t  imu_gbias[3]  = {0, 0, 0};   /* raw gyro bias, LSB */
static uint32_t imu_last_tick = 0;
static uint32_t imu_prev_tick = 0;
static uint32_t imu_updates   = 0;
static uint32_t imu_errors    = 0;

/* 1 while the live geometry differs from what is stored in flash. Tracked in
 * firmware so a GUI that connects later still learns whether the layout on the
 * aircraft is saved. */
static uint8_t cfg_dirty = 1;

/* ── Soft start/stop for 380KV @ 24V (9120 RPM no-load) ─────
 * Large prop inertia + 500Hz update needs slew limiting to avoid
 * current spikes on instant 0→20% (1000→1200us) steps.
 * RAMP_STEP_US per RAMP_INTERVAL_MS = slew rate.
 *   4us / 5ms = 800us/sec => 0→20% (200us) in 250ms, full 0→100% in 1.25s
 *   3us / 5ms = 600us/sec => 0→20% in 333ms (smoother)
 *   6us / 5ms = 1200us/sec => 0→20% in 167ms (more aggressive)
 * Tune STEP to taste — increase for faster, decrease for smoother.
 */
#define RAMP_STEP_US      4
#define RAMP_INTERVAL_MS  5

/* ── UART RX ──────────────────────────────────────────────── */
volatile char rx_buf[32];
volatile uint8_t rx_idx = 0;
volatile uint8_t cmd_ready = 0;

/* Forward declarations */
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART2_UART_Init(void);
static void MX_Timers_Init(void);
static void uart_send_char(uint8_t c);
static void uart_send_str(const char *s);
static void uart_send_uint(uint32_t v);
static void uart_send_int(int32_t v);
static void uart_send_hex8(uint8_t v);
static void process_cmd(void);
static void send_mixer_config(void);
static void send_battery(void);
static void send_pmu_identity(void);
static void send_mix_state(void);
static void mix_zero_in(void);
static void imu_init(void);
static void imu_poll(void);
static void imu_zero_gyro(void);
static void imu_status(void);
uint32_t system_millis(void);
void     delay_ms(uint32_t ms);
void     delay_us(uint32_t us);

/* low-level: write CCR immediately (no ramp) */
static void apply_ccr(uint8_t motor, uint32_t ccr) {
    if (motor >= 6) return;
    motor_ccr[motor] = ccr;
    const MotorConfig *m = &motors[motor];
    switch (m->channel) {
        case LL_TIM_CHANNEL_CH1: LL_TIM_OC_SetCompareCH1(m->tim, ccr); break;
        case LL_TIM_CHANNEL_CH2: LL_TIM_OC_SetCompareCH2(m->tim, ccr); break;
        case LL_TIM_CHANNEL_CH3: LL_TIM_OC_SetCompareCH3(m->tim, ccr); break;
        case LL_TIM_CHANNEL_CH4: LL_TIM_OC_SetCompareCH4(m->tim, ccr); break;
        default: break;
    }
}

/* high-level: set target — ramp will slew actual toward it */
static void set_target(uint8_t motor, uint32_t ccr) {
    if (motor >= 6) return;
    if (ccr < 1000) ccr = 1000;
    if (ccr > 2000) ccr = 2000;
    motor_target[motor] = ccr;
}

/* instant set (used for ARM/DISARM sync to avoid ramp delay at boundaries) */
static void set_throttle(uint8_t motor, uint32_t ccr) {
    set_target(motor, ccr);
    apply_ccr(motor, ccr);  /* sync actual immediately for now — ramp will keep it */
}

/* called every RAMP_INTERVAL_MS from main loop */
static void ramp_update(void) {
    for (uint8_t i = 0; i < 6; i++) {
        if (motor_ccr[i] < motor_target[i]) {
            uint32_t diff = motor_target[i] - motor_ccr[i];
            uint32_t step = diff < RAMP_STEP_US ? diff : RAMP_STEP_US;
            apply_ccr(i, motor_ccr[i] + step);
        } else if (motor_ccr[i] > motor_target[i]) {
            uint32_t diff = motor_ccr[i] - motor_target[i];
            uint32_t step = diff < RAMP_STEP_US ? diff : RAMP_STEP_US;
            apply_ccr(i, motor_ccr[i] - step);
        }
    }
}

int main(void)
{
    LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_SYSCFG);
    LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_PWR);
    SystemClock_Config();
    MX_GPIO_Init();
    MX_Timers_Init();
    MX_USART2_UART_Init();
    while((!(LL_USART_IsActiveFlag_TEACK(USART2))) || (!(LL_USART_IsActiveFlag_REACK(USART2))));
    LL_USART_EnableIT_RXNE(USART2);

    SysTick_Config(48000000 / 1000);

    /* Mixer geometry: restore the saved layout if there is one, otherwise
     * fall back to the Hexa-X default. Either way report it so the GUI can
     * populate; CFG,LOADED also tells the GUI the geometry is persisted. */
    mixer_init();
    if (mixer_load() == 0) {
        cfg_dirty = 0;
        uart_send_str("CFG,LOADED\r\n");
    } else {
        cfg_dirty = 1;                  /* default layout is not stored yet */
        uart_send_str("CFG,DEFAULT\r\n");
    }
    send_mixer_config();

    /* Power module (PM02D / INA228 on I2C1 PB8/PB9, AF auto-detected).
     * Optional: if it is not connected, probing is bounded and the module is
     * simply left offline — the mixer and ESC control run unaffected. */
    static uint8_t pmu_was_online = 0;
    i2c_select(1);                 /* PMU lives on I2C1 (PB8/PB9) */
    if (pmu_init() == 0) {
        const pmu_data_t *p = pmu_data();
        uart_send_str("PMU,");
        uart_send_str(p->chip == 2 ? "INA228" : "INA226");
        uart_send_char(',');
        uart_send_uint(p->addr);
        uart_send_str("\r\n");
        pmu_was_online = 1;
    } else {
        uart_send_str("PMU,NONE\r\n");
    }
    uart_send_str("DISARMED\r\n");

    imu_init();                    /* ISM330IS on I2C2 + MotionFX 6X */

    uint32_t last_telem = 0;
    uint32_t last_ramp = 0;
    uint32_t last_pmu = 0;
    uint32_t last_batt = 0;
    while (1) {
        if (cmd_ready) { cmd_ready = 0; process_cmd(); }

        /* Deferred reporting of an emergency stop / recovery. Done here rather
         * than in the ISR so the message cannot be spliced into the middle of
         * a telemetry line, and so the mixer-state line is always sent after
         * the state change it describes. */
        if (kill_event) {
            uint8_t ev = kill_event;
            kill_event = 0;
            uart_send_str(ev == 1 ? "KILLED\r\n" : "DISARMED\r\n");
            send_mix_state();
        }

        /* soft ramp: slew actual toward target */
        if ((sys_tick - last_ramp) >= RAMP_INTERVAL_MS) {
            last_ramp = sys_tick;
            ramp_update();
        }

        if (motor_state == ST_ARMED && (sys_tick - last_cmd_tick) > 1000) {
            motor_state = ST_DISARMED;
            for (int i = 0; i < 6; i++) set_target(i, 1000);  /* soft stop via ramp */
            uart_send_str("TIMEOUT\r\n");
        }

        if ((sys_tick - last_telem) >= 100) {
            last_telem = sys_tick;
            uart_send_char('T');
            for (int i = 0; i < 6; i++) { uart_send_uint(motor_ccr[i]); uart_send_char(','); }
            uart_send_char('0' + motor_state);
            uart_send_str("\r\n");
        }

        /* NOTE: the PMU is deliberately NOT auto-re-probed here. A failed
         * probe blocks the loop for ~240 ms (I2C timeouts), which starves the
         * IMU fusion and makes the attitude jump. The PMU is probed at boot
         * and on demand ('B' from a dashboard); losing it costs the IMU zero.
         * pmu_read() is a no-op while offline, so the loop stays fast. */

        /* Power module: sample at 10 Hz (counters use the real elapsed time),
         * report to the GUI at 5 Hz. */
        if ((sys_tick - last_pmu) >= 100) {
            uint32_t dt = sys_tick - last_pmu;
            last_pmu = sys_tick;
            i2c_select(1);
            (void)pmu_read(dt);
        }
        if ((sys_tick - last_batt) >= 200) {
            last_batt = sys_tick;
            if (pmu_data()->chip != 0) {
                send_battery();
            } else if (pmu_was_online) {
                /* the module stopped answering: tell the GUI once */
                pmu_was_online = 0;
                uart_send_str("PMU,LOST\r\n");
            }
        }

        if (imu_ok) imu_poll();

        if (motor_state == ST_ARMED) {
            LL_GPIO_SetOutputPin(LED_GREEN_PORT, LED_GREEN_PIN);
            LL_GPIO_ResetOutputPin(LED_BLUE_PORT, LED_BLUE_PIN);
        } else if (motor_state == ST_KILLED) {
            LL_GPIO_ResetOutputPin(LED_GREEN_PORT, LED_GREEN_PIN);
            LL_GPIO_SetOutputPin(LED_BLUE_PORT, LED_BLUE_PIN);
        } else {
            LL_GPIO_ResetOutputPin(LED_GREEN_PORT, LED_GREEN_PIN);
            LL_GPIO_ResetOutputPin(LED_BLUE_PORT, LED_BLUE_PIN);
        }
    }
}

void SystemClock_Config(void) {
    LL_FLASH_SetLatency(LL_FLASH_LATENCY_1);
    LL_RCC_HSI_Enable(); while(LL_RCC_HSI_IsReady() != 1);
    LL_RCC_HSI_SetCalibTrimming(64);
    LL_RCC_SetHSIDiv(LL_RCC_HSI_DIV_1);
    LL_RCC_SetAHBPrescaler(LL_RCC_HCLK_DIV_1);
    LL_RCC_SetSYSDivider(LL_RCC_SYSCLK_DIV_1);
    LL_RCC_SetSysClkSource(LL_RCC_SYS_CLKSOURCE_HSI);
    while(LL_RCC_GetSysClkSource() != LL_RCC_SYS_CLKSOURCE_STATUS_HSI);
    LL_RCC_SetAPB1Prescaler(LL_RCC_APB1_DIV_1);
    LL_Init1msTick(48000000);
    LL_SetSystemCoreClock(48000000);
}

static void MX_GPIO_Init(void) {
    LL_IOP_GRP1_EnableClock(LL_IOP_GRP1_PERIPH_GPIOA);
    LL_IOP_GRP1_EnableClock(LL_IOP_GRP1_PERIPH_GPIOC);

    LL_GPIO_InitTypeDef g = {0};
    g.Pin = LED_GREEN_PIN; g.Mode = LL_GPIO_MODE_OUTPUT; g.Speed = LL_GPIO_SPEED_FREQ_LOW;
    g.OutputType = LL_GPIO_OUTPUT_PUSHPULL; g.Pull = LL_GPIO_PULL_NO;
    LL_GPIO_Init(LED_GREEN_PORT, &g);

    g.Pin = LED_BLUE_PIN;
    LL_GPIO_Init(LED_BLUE_PORT, &g);

    g.Pin = BUTTON_PIN; g.Mode = LL_GPIO_MODE_INPUT; g.Pull = LL_GPIO_PULL_UP;
    LL_GPIO_Init(BUTTON_PORT, &g);

    LL_EXTI_InitTypeDef e = {0};
    e.Line_0_31 = LL_EXTI_LINE_13; e.LineCommand = ENABLE;
    e.Mode = LL_EXTI_MODE_IT; e.Trigger = LL_EXTI_TRIGGER_FALLING;
    LL_EXTI_Init(&e);
    LL_EXTI_SetEXTISource(LL_EXTI_CONFIG_PORTC, LL_EXTI_CONFIG_LINE13);
    NVIC_SetPriority(EXTI4_15_IRQn, 3); NVIC_EnableIRQ(EXTI4_15_IRQn);
}

static void init_one_timer(const MotorConfig *m) {
    if (m->tim == TIM1)  LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_TIM1);
    if (m->tim == TIM2)  LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_TIM2);
    if (m->tim == TIM14) LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_TIM14);
    if (m->tim == TIM16) LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_TIM16);
    if (m->tim == TIM17) LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_TIM17);
}

static void MX_Timers_Init(void) {
    for (uint8_t i = 0; i < 6; i++) {
        const MotorConfig *m = &motors[i];
        init_one_timer(m);

        LL_GPIO_InitTypeDef g = {0};
        g.Pin = m->pin; g.Mode = LL_GPIO_MODE_ALTERNATE;
        g.Speed = LL_GPIO_SPEED_FREQ_HIGH; g.OutputType = LL_GPIO_OUTPUT_PUSHPULL;
        g.Pull = LL_GPIO_PULL_NO; g.Alternate = m->af;
        LL_GPIO_Init(m->port, &g);

        LL_TIM_SetPrescaler(m->tim, 47);          /* 48MHz/48 = 1MHz tick */
        LL_TIM_SetAutoReload(m->tim, 1999);        /* 1MHz/2000 = 500Hz (period 2ms, 1-2ms = 50-100% duty) */

        /* Set initial compare value for the correct channel */
        switch (m->channel) {
            case LL_TIM_CHANNEL_CH1: LL_TIM_OC_SetCompareCH1(m->tim, 1000); break;
            case LL_TIM_CHANNEL_CH2: LL_TIM_OC_SetCompareCH2(m->tim, 1000); break;
            case LL_TIM_CHANNEL_CH3: LL_TIM_OC_SetCompareCH3(m->tim, 1000); break;
            case LL_TIM_CHANNEL_CH4: LL_TIM_OC_SetCompareCH4(m->tim, 1000); break;
            default: break;
        }

        LL_TIM_OC_SetMode(m->tim, m->channel, LL_TIM_OCMODE_PWM1);
        LL_TIM_OC_SetPolarity(m->tim, m->channel, LL_TIM_OCPOLARITY_HIGH);
        LL_TIM_CC_EnableChannel(m->tim, m->channel);
        LL_TIM_EnableAllOutputs(m->tim);
        LL_TIM_EnableCounter(m->tim);
    }
}

static void MX_USART2_UART_Init(void) {
    LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_USART2);
    LL_GPIO_InitTypeDef g = {0};
    g.Pin = LL_GPIO_PIN_2|LL_GPIO_PIN_3; g.Mode = LL_GPIO_MODE_ALTERNATE;
    g.Speed = LL_GPIO_SPEED_FREQ_HIGH; g.OutputType = LL_GPIO_OUTPUT_PUSHPULL;
    g.Pull = LL_GPIO_PULL_UP; g.Alternate = LL_GPIO_AF_1;
    LL_GPIO_Init(GPIOA, &g);
    NVIC_SetPriority(USART2_IRQn, 0); NVIC_EnableIRQ(USART2_IRQn);
    LL_USART_InitTypeDef u = {0};
    u.PrescalerValue = LL_USART_PRESCALER_DIV1; u.BaudRate = 115200;
    u.DataWidth = LL_USART_DATAWIDTH_8B; u.StopBits = LL_USART_STOPBITS_1;
    u.Parity = LL_USART_PARITY_NONE; u.TransferDirection = LL_USART_DIRECTION_TX_RX;
    u.HardwareFlowControl = LL_USART_HWCONTROL_NONE; u.OverSampling = LL_USART_OVERSAMPLING_16;
    LL_USART_Init(USART2, &u);
    LL_USART_ConfigAsyncMode(USART2);
    LL_USART_Enable(USART2);
}

/* ── UART helpers ── */
static void uart_send_char(uint8_t c) { while(!LL_USART_IsActiveFlag_TXE(USART2)); LL_USART_TransmitData8(USART2, c); }
static void uart_send_str(const char *s) { while(*s) uart_send_char(*s++); }
static void uart_send_uint(uint32_t v) {
    char b[12]; int i=0;
    if(v==0){uart_send_char('0');return;}
    while(v>0){b[i++]='0'+(v%10);v/=10;}
    while(i>0)uart_send_char(b[--i]);
}

static void uart_send_int(int32_t v) {
    if (v < 0) { uart_send_char('-'); uart_send_uint((uint32_t)(-(int64_t)v)); }
    else       { uart_send_uint((uint32_t)v); }
}

static void uart_send_hex8(uint8_t v) {
    static const char hx[] = "0123456789ABCDEF";
    uart_send_char(hx[(v >> 4) & 0xFu]);
    uart_send_char(hx[v & 0xFu]);
}

/* ── Mixer / PMU reporting ── */
/* Machine readable mixer geometry: Q,<angle>,<dir> x6 ; limit name */
static const char *mixer_limit_name(mixer_limit_t l) {
    switch (l) {
        case MIX_SHIFTED: return "SHIFTED";
        case MIX_SCALED:  return "SCALED";
        default:          return "OK";
    }
}

static void send_mixer_config(void) {
    uart_send_char('Q');
    for (int i = 0; i < 6; i++) {
        uart_send_char(',');
        uart_send_int(mixer_motors[i].angle_deg);
        uart_send_char(',');
        uart_send_int(mixer_motors[i].enabled ? mixer_motors[i].yaw_dir : 0);
    }
    uart_send_str("\r\n");
}

/* Report the commanded mixer inputs. Sent whenever the firmware (not the GUI)
 * changes them: on kill, on arm and on request, so a GUI can never keep
 * displaying a command the firmware has already dropped. */
static void send_mix_state(void) {
    uart_send_str("MIX,");
    uart_send_int(mix_in[0]); uart_send_char(',');
    uart_send_int(mix_in[1]); uart_send_char(',');
    uart_send_int(mix_in[2]); uart_send_char(',');
    uart_send_int(mix_in[3]);
    uart_send_str("\r\n");
}

/* Clear the commanded mixer inputs: throttle to idle, attitude to centre.
 * Throttle is in microseconds, so "zero throttle" is 1000 us, not 0 us — a
 * 0 us pulse is not a valid ESC signal and the limiter would only push it
 * back up to the minimum anyway. */
static void mix_zero_in(void) {
    mix_in[0] = MIXER_MIN_US;
    mix_in[1] = 0;
    mix_in[2] = 0;
    mix_in[3] = 0;
}

/* PMU identity line, so a GUI that attached after boot can still learn it */
static void send_pmu_identity(void) {
    const pmu_data_t *p = pmu_data();
    if (p->chip == 0) {
        uart_send_str("PMU,NONE\r\n");
        return;
    }
    uart_send_str("PMU,");
    uart_send_str(p->chip == 2 ? "INA228" : "INA226");
    uart_send_char(',');
    uart_send_uint(p->addr);
    uart_send_str("\r\n");
}

/* Battery snapshot, integer base units: B,<mV>,<mA>,<mW>,<uAh>,<uWh>,<mC> */
static void send_battery(void) {
    const pmu_data_t *p = pmu_data();
    uart_send_char('B');
    uart_send_char(',');
    uart_send_int(p->vbus_mv);
    uart_send_char(',');
    uart_send_int(p->current_ma);
    uart_send_char(',');
    uart_send_int(p->power_mw);
    uart_send_char(',');
    uart_send_int((int32_t)p->charge_uah);
    uart_send_char(',');
    uart_send_int((int32_t)p->energy_uwh);
    uart_send_char(',');
    if (p->temp_mc == INT32_MIN) { uart_send_str("na"); }
    else                         { uart_send_int(p->temp_mc); }
    uart_send_str("\r\n");
}

/* Run the mixer and report: <'X' applied | 'Y' dry-run>,outs...,limit,thr_used */
static void run_mixer(char tag, int32_t thr, int32_t roll, int32_t pitch, int32_t yaw) {
    mixer_result_t r;
    mixer_apply(thr, roll, pitch, yaw, &r);

    if (tag == 'X') {
        for (int i = 0; i < 6; i++) set_target((uint8_t)i, r.out[i]);
        last_cmd_tick = sys_tick;          /* a mix command is a live command */
        /* remember the accepted command as the authoritative mixer state */
        mix_in[0] = thr; mix_in[1] = roll; mix_in[2] = pitch; mix_in[3] = yaw;
    }

    uart_send_char((char)tag);
    for (int i = 0; i < 6; i++) {
        uart_send_char(',');
        uart_send_uint(r.out[i]);
    }
    uart_send_char(',');
    uart_send_str(mixer_limit_name(r.limit));
    uart_send_char(',');
    uart_send_int(r.thr_used);
    uart_send_str("\r\n");
}

/* Read up to n comma separated ints (supports negatives). Returns count. */
static int parse_csv_ints(const char *s, int32_t *out, int n) {
    int cnt = 0;
    while (cnt < n && *s) {
        int32_t sign = 1, v = 0;
        if (*s == '-') { sign = -1; s++; }
        while (*s >= '0' && *s <= '9') { v = v*10 + (*s - '0'); s++; }
        out[cnt++] = sign * v;
        while (*s && *s != ',') s++;
        if (*s == ',') s++;
    }
    return cnt;
}

/* ── Emergency stop ──────────────────────────────────────────────────────
 * One implementation of the safety action, shared by the PC13 button ISR and
 * the `!` command so the two can never drift apart. */
static void emergency_kill(void) {
    if (motor_state == ST_KILLED) return;

    /* Force idle, then disable the timer outputs outright: an ESC receiving no
     * signal is safer than one receiving a stale 1000 us pulse. */
    motor_state = ST_KILLED;
    for (int i = 0; i < 6; i++) {
        motor_target[i] = 1000;
        apply_ccr(i, 1000);
        LL_TIM_DisableAllOutputs(motors[i].tim);
    }

    /* Zero the commanded mixer inputs too, so throttle/roll/pitch/yaw all read
     * zero. Without this the GUI would keep its last sliders and a later
     * re-arm would resume from a stale, possibly high, command. */
    mix_zero_in();
    kill_event = 1;                    /* reported from the main loop */
}

/* Leave the killed state: outputs re-enabled, but DISARMED (never straight
 * back to armed), and the mixer inputs stay zeroed. */
static void emergency_recover(void) {
    if (motor_state != ST_KILLED) return;
    for (int i = 0; i < 6; i++) LL_TIM_EnableAllOutputs(motors[i].tim);
    motor_state = ST_DISARMED;
    mix_zero_in();
    kill_event = 2;
}

/* ── Command parser ── */
static uint32_t parse_uint(const char *s) {
    uint32_t v = 0;
    while (*s >= '0' && *s <= '9') { v = v*10 + (*s-'0'); s++; }
    return v;
}

static void process_cmd(void) {
    char *c = (char*)rx_buf;

    if (c[0] == 'A') {
        if (motor_state == ST_KILLED) {
            /* Never silently ignore an arm request: the operator needs to know
             * why nothing happened and how to get out of it. */
            uart_send_str("AE,KILLED\r\n");
        } else {
            motor_state = ST_ARMED; last_cmd_tick = sys_tick;
            for (int i = 0; i < 6; i++) { motor_target[i]=1000; apply_ccr(i,1000); } /* instant 1000 at arm */
            mix_zero_in();               /* always start from idle + centred */
            uart_send_str("ARMED\r\n");
            send_mix_state();
        }
    }
    else if (c[0] == 'D') {
        motor_state = ST_DISARMED;
        for (int i = 0; i < 6; i++) set_target(i, 1000);  /* soft stop — ramps down */
        mix_zero_in();
        uart_send_str("DISARMED\r\n");
        send_mix_state();
    }
    else if (c[0] == 'R') {
        emergency_recover();
    }
    /* Emergency stop from the ground station. Deliberately a punctuation
     * character so line noise cannot trigger it by accident. */
    else if (c[0] == '!') {
        emergency_kill();
    }
    else if (c[0] == 'S' && motor_state == ST_ARMED) {
        /* Format: S<motor>,<value>  e.g. S1,1500
           Backward compat: S<value> → sets all motors
           Soft: sets target, ramp_update() slews actual */
        char *p = &c[1];
        uint32_t v1 = parse_uint(p);
        while (*p >= '0' && *p <= '9') p++;
        if (*p == ',') {
            p++;
            uint32_t val = parse_uint(p);
            set_target((uint8_t)(v1 - 1), val);
        } else {
            for (int i = 0; i < 6; i++) set_target(i, v1);
        }
        last_cmd_tick = sys_tick;
    }
    else if (c[0] == 'K') {
        /* Keepalive: feeds the watchdog without touching any output. */
        last_cmd_tick = sys_tick;
    }
    /* ── Mixer geometry configuration ───────────────────────────────── */
    else if (c[0] == 'Q') {
        send_mixer_config();
        send_mix_state();                    /* let a fresh GUI sync its sliders */
        uart_send_str(cfg_dirty ? "CFG,DIRTY\r\n" : "CFG,SAVED\r\n");
    }
    else if (c[0] == 'P') {
        int p = mixer_preset_from_char(c[1]);
        if (p > 0) {
            mixer_load_preset((mixer_preset_t)p);
            send_mixer_config();
            cfg_dirty = 1;
            uart_send_str("CFG,DIRTY\r\n");
        } else {
            uart_send_str("PE,BAD_PRESET\r\n");
        }
    }
    else if (c[0] == 'C') {
        /* Commit the current geometry so it survives reset and power-off. */
        int rc = mixer_save();
        if (rc == 0) { cfg_dirty = 0; uart_send_str("CFG,SAVED\r\n"); }
        else         { uart_send_str("CFG,SAVE_ERR,"); uart_send_int(rc); uart_send_str("\r\n"); }
    }
    else if (c[0] == 'M') {
        /* M<motor>,<angle_deg>,<yaw_dir>  —  motor is 1-based */
        int32_t a[3];
        if (parse_csv_ints(&c[1], a, 3) == 3) {
            if (a[2] != 1 && a[2] != -1) {
                uart_send_str("ME,BAD_DIR\r\n");
            } else if (mixer_set_motor((int)a[0] - 1, (int)a[1], (int)a[2]) != 0) {
                uart_send_str("ME,BAD_MOTOR\r\n");
            } else {
                const mixer_motor_t *m = &mixer_motors[a[0] - 1];
                uart_send_str("MK,");
                uart_send_int(a[0]);   uart_send_char(',');
                uart_send_int(m->angle_deg); uart_send_char(',');
                uart_send_int(m->yaw_dir);
                uart_send_str("\r\n");
                cfg_dirty = 1;
                uart_send_str("CFG,DIRTY\r\n");
            }
        } else {
            uart_send_str("ME,BAD_ARGS\r\n");
        }
    }
    /* ── Mixer input: X applies (armed only), Y is a dry run ─────────── */
    else if (c[0] == 'X' || c[0] == 'Y') {
        int32_t a[4];
        if (parse_csv_ints(&c[1], a, 4) == 4) {
            if (c[0] == 'X' && motor_state != ST_ARMED) {
                uart_send_str("XE,NOT_ARMED\r\n");
            } else {
                run_mixer(c[0], a[0], a[1], a[2], a[3]);
            }
        } else {
            uart_send_str("XE,BAD_ARGS\r\n");
        }
    }
    /* ── Power module ───────────────────────────────────────────────── */
    else if (c[0] == 'B') {
        if (!pmu_is_online()) {
            pmu_init();          /* allow plugging the module in later */
        }
        send_pmu_identity();
        send_battery();
    }
    else if (c[0] == 'Z') {
        pmu_zero_counters();
        uart_send_str("COUNTERS,ZEROED\r\n");
    }
    else if (c[0] == 'W') {
        /* Verbose mixer table: angle, dir and the derived gains */
        for (int i = 0; i < 6; i++) {
            const mixer_motor_t *m = &mixer_motors[i];
            uart_send_char('W');
            uart_send_uint(i + 1);      uart_send_char(',');
            uart_send_int(m->angle_deg);uart_send_char(',');
            uart_send_int(m->yaw_dir);  uart_send_char(',');
            uart_send_int(m->enabled);  uart_send_char(',');
            uart_send_int(m->roll_gain);uart_send_char(',');
            uart_send_int(m->pitch_gain);
            uart_send_str("\r\n");
        }
    }
    /* ── IMU: lowercase letters (uppercase belong to the motor/mixer) ── */
    else if (c[0] == '?') {
        imu_status();
    }
    else if (c[0] == 'a') {          /* start fused E stream */
        imu_stream = 1;
        uart_send_str("IMU,STREAM,ON\r\n");
    }
    else if (c[0] == 'x') {          /* stop fused E stream */
        imu_stream = 0;
        uart_send_str("IMU,STREAM,OFF\r\n");
    }
    else if (c[0] == 'z') {          /* zero gyro bias (hold still) */
        imu_zero_gyro();
    }
}

/* ── system/delay helpers (used by the IMU i2c + ism drivers) ── */
uint32_t system_millis(void) { return sys_tick; }
void delay_ms(uint32_t ms) { uint32_t t = sys_tick; while ((sys_tick - t) < ms) { } }
void delay_us(uint32_t us) { for (volatile uint32_t i = 0; i < us * 10u; i++) { } }

/* ── IMU: ISM330IS on I2C2 (PB10/PB11) + MotionFX 6X fusion ── */
static void imu_init(void)
{
    i2c_select(2);
    /* I2C2 on PB10 (CN10-34) / PB11 (CN7-37); AF6 verified on hardware. */
    if (i2c_init_on_pins2('B', 10u, 6u, 'B', 11u, 6u) != 0) {
        uart_send_str("IMU,NONE\r\n");
        return;
    }
    uint8_t addr = 0u, who = 0u;
    int rc = ism_init(&addr, &who);
    if (rc == 0) {
        fusion_init();
        imu_ok = 1;
        imu_prev_tick = sys_tick;
        uart_send_str("IMU,ISM330IS,0x");
        uart_send_hex8(addr);
        uart_send_str("\r\n");
    } else if (rc == -2) {
        uart_send_str("IMU,BAD_ID,"); uart_send_uint(who); uart_send_str("\r\n");
    } else {
        uart_send_str("IMU,NONE\r\n");
    }
}

static void send_imu_line(const fusion_euler_t *e)
{
    uart_send_char('E'); uart_send_char(',');
    uart_send_uint(sys_tick);        uart_send_char(',');
    uart_send_int(e->roll_mdeg);     uart_send_char(',');
    uart_send_int(e->pitch_mdeg);    uart_send_char(',');
    uart_send_int(e->yaw_mdeg);      uart_send_char(',');
    uart_send_int(e->gbias_mdps[0]); uart_send_char(',');
    uart_send_int(e->gbias_mdps[1]); uart_send_char(',');
    uart_send_int(e->gbias_mdps[2]);
    uart_send_str("\r\n");
}

static void imu_poll(void)
{
    if ((sys_tick - imu_last_tick) < 10u) return;      /* 100 Hz */
    imu_last_tick = sys_tick;

    i2c_select(2);
    ism_sample_t s;
    if (ism_read_sample(&s) != 0) { imu_errors++; return; }

    float dt = (float)(sys_tick - imu_prev_tick) / 1000.0f;
    imu_prev_tick = sys_tick;
    /* Clamp outliers: if the loop was briefly delayed, feed the nominal period
     * instead of a huge dt (a big dt makes MotionFX swing the attitude). */
    if (dt <= 0.0f || dt > 0.05f) dt = 0.01f;

    ism_sample_t b = s;
    b.gx = (int16_t)(s.gx - imu_gbias[0]);
    b.gy = (int16_t)(s.gy - imu_gbias[1]);
    b.gz = (int16_t)(s.gz - imu_gbias[2]);

    fusion_euler_t e;
    if (fusion_step(&b, dt, &e) == 0) {
        imu_updates++;
        if (imu_stream) send_imu_line(&e);
    }
}

static void imu_zero_gyro(void)
{
    if (!imu_ok) { uart_send_str("IMU,NONE\r\n"); return; }
    int64_t ax = 0, ay = 0, az = 0; int n = 0;
    for (int i = 0; i < 200; i++) {
        i2c_select(2);
        ism_sample_t s;
        if (ism_read_sample(&s) == 0) { ax += s.gx; ay += s.gy; az += s.gz; n++; }
        delay_ms(5);
    }
    if (n > 0) { imu_gbias[0] = (int32_t)(ax/n); imu_gbias[1] = (int32_t)(ay/n); imu_gbias[2] = (int32_t)(az/n); }
    uart_send_str("IMU,GYRO_ZEROED,");
    uart_send_int(imu_gbias[0]); uart_send_char(',');
    uart_send_int(imu_gbias[1]); uart_send_char(',');
    uart_send_int(imu_gbias[2]); uart_send_str("\r\n");
}

static void imu_status(void)
{
    uart_send_str("# ---- status ----\r\n# IMU      : ");
    if (imu_ok) { uart_send_str("ISM330IS @0x"); uart_send_hex8(ism_addr()); }
    else          uart_send_str("not detected");
    uart_send_str("\r\n# fusion   : "); uart_send_uint(imu_updates);
    uart_send_str(" updates, stream "); uart_send_str(imu_stream ? "ON" : "OFF");
    uart_send_str("\r\n# imu errs : "); uart_send_uint(imu_errors);
    uart_send_str("\r\n");
}

/* ── IRQ Handlers ── */
void SysTick_Handler(void) { sys_tick++; }

void USART2_IRQHandler(void) {
    if (LL_USART_IsActiveFlag_RXNE(USART2)) {
        uint8_t b = LL_USART_ReceiveData8(USART2);
        if (b == '\n') { rx_buf[rx_idx] = 0; cmd_ready = 1; rx_idx = 0; }
        else if (rx_idx < 31) rx_buf[rx_idx++] = b;
    }
    if (LL_USART_IsActiveFlag_ORE(USART2)) LL_USART_ClearFlag_ORE(USART2);
    if (LL_USART_IsActiveFlag_FE(USART2))  LL_USART_ClearFlag_FE(USART2);
}

void EXTI4_15_IRQHandler(void) {
    if (LL_EXTI_IsActiveFallingFlag_0_31(LL_EXTI_LINE_13)) {
        LL_EXTI_ClearFallingFlag_0_31(LL_EXTI_LINE_13);
        if (motor_state == ST_KILLED) {
            emergency_recover();
        } else {
            emergency_kill();
        }
    }
}
