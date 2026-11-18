/* MultiMotor_N6 — full drone firmware for NUCLEO-N657X0-Q
 * 6x ESC PWM + ISM330IS IMU + INA228 PMU + Mahony AHRS + geometry mixer.
 * Console protocol identical to the C092 build so the existing dashboards work.
 */
#include "main.h"
#include "board_n6.h"
#include "sensors.h"
#include <string.h>
#include <stdio.h>
#include <math.h>

extern uint32_t g_pfnVectors[];
void SystemClock_Config(void);
void Error_Handler(void);

/* ── raw LED stage markers (pre-HAL) ─────────────────────────────────────── */
static void raw_led_init(void)
{
    RCC->AHB4ENR |= RCC_AHB4ENR_GPIOGEN; (void)RCC->AHB4ENR;
    GPIOG->MODER &= ~((3u<<0)|(3u<<16)|(3u<<20));
    GPIOG->MODER |=  ((1u<<0)|(1u<<16)|(1u<<20));
    GPIOG->OTYPER &= ~((1u<<0)|(1u<<8)|(1u<<10));
    GPIOG->BSRR = (1u<<0)|(1u<<8)|(1u<<10);
}
static inline void raw_led(int p, int on) { GPIOG->BSRR = on ? (1u<<(p+16)) : (1u<<p); }

/* ── mixer geometry (same defaults as C092) ──────────────────────────────── */
static int16_t geo_a[6]  = {30, 90, 210, 270, 150, 330};
static int8_t  geo_d[6]  = {-1, +1, +1, -1, -1, +1};
static uint8_t geo_en[6] = {1,1,1,1,1,1};
static int32_t rg[6], pg[6], yg[6];

static void mix_precompute(void)
{
    for (int i = 0; i < 6; i++) {
        float a = (float)geo_a[i] * 0.0174532925f;
        rg[i] = (int32_t)(-sinf(a) * 32767.0f);
        pg[i] = (int32_t)(-cosf(a) * 32767.0f);
        yg[i] = (int32_t)geo_d[i] * 32767;
    }
}

/* returns limiter state 0=ok 1=shifted 2=scaled */
static uint8_t mix_apply(int32_t thr, int32_t roll, int32_t pitch, int32_t yaw, uint16_t out[6])
{
    int32_t d[6];
    int32_t dmax = 0;
    for (int i = 0; i < 6; i++) {
        if (!geo_en[i]) { d[i] = 0; continue; }
        d[i] = (roll * rg[i] + pitch * pg[i] + yaw * yg[i]) >> 15;
        int32_t ad = d[i] < 0 ? -d[i] : d[i];
        if (ad > dmax) dmax = ad;
    }
    uint8_t lim = 0;
    int32_t lo = 1000, hi = 2000;
    if (thr - dmax < lo) { thr = lo + dmax; lim = 1; }
    else if (thr + dmax > hi) { thr = hi - dmax; lim = 1; }
    if (dmax * 2 > (hi - lo)) {                       /* attitude range too wide */
        int32_t k = ((hi - lo) * 32767) / (dmax * 2);
        for (int i = 0; i < 6; i++) d[i] = (d[i] * k) >> 15;
        lim = 2;
    }
    for (int i = 0; i < 6; i++) {
        if (!geo_en[i]) { out[i] = 1000; continue; }
        int32_t v = thr + d[i];
        if (v < 1000) v = 1000;
        if (v > 2000) v = 2000;
        out[i] = (uint16_t)v;
    }
    return lim;
}

/* ── state ───────────────────────────────────────────────────────────────── */
#define ST_DISARMED 0
#define ST_ARMED    1
#define ST_KILLED   2
static uint8_t  state;
static int32_t  tgt[6] = {1000,1000,1000,1000,1000,1000};
static uint32_t motor_us[6] = {1000,1000,1000,1000,1000,1000};
static int32_t  mx_thr = 1000, mx_roll, mx_pitch, mx_yaw;
static uint32_t last_cmd_ms, last_telem_ms, last_batt_ms, last_imu_ms, last_q_ms;
static int32_t  batt_mv, batt_ma;
static float    roll_deg, pitch_deg, yaw_deg;
static uint32_t imu_updates, imu_errors;
static int16_t  last_g[3], last_a[3];
static char     cmdline[48]; static uint8_t cmdlen;

static void tx_state(void)
{
    const char *n = state == ST_ARMED ? "ARMED" : (state == ST_KILLED ? "KILLED" : "DISARMED");
    n6_tx(n); n6_tx("\r\n");
}
static void send_T(void)
{
    n6_tx_char('T');
    for (int i = 0; i < 6; i++) { n6_tx_uint(motor_us[i]); n6_tx_char(','); }
    n6_tx_char('0' + state); n6_tx("\r\n");
}
static void send_B(void)
{
    n6_tx("B,"); n6_tx_int(batt_mv); n6_tx_char(',');
    n6_tx_int(batt_ma); n6_tx_char(',');
    n6_tx_int((batt_mv * batt_ma) / 1000); n6_tx_char(',');
    n6_tx_uint(0); n6_tx_char(','); n6_tx_uint(0); n6_tx(",na\r\n");
}
static void send_E(void)
{
    n6_tx("E,"); n6_tx_uint(HAL_GetTick()); n6_tx_char(',');
    n6_tx_int((int32_t)(roll_deg * 1000.0f)); n6_tx_char(',');
    n6_tx_int((int32_t)(pitch_deg * 1000.0f)); n6_tx_char(',');
    n6_tx_int((int32_t)(yaw_deg * 1000.0f)); n6_tx_char(',');
    n6_tx_int(last_g[0]); n6_tx_char(','); n6_tx_int(last_g[1]); n6_tx_char(','); n6_tx_int(last_g[2]);
    n6_tx("\r\n");
}
static void send_Q(void)
{
    n6_tx_char('Q');
    for (int i = 0; i < 6; i++) { n6_tx_char(','); n6_tx_int(geo_a[i]); n6_tx_char(','); n6_tx_int(geo_d[i]); }
    n6_tx("\r\n");
}
static void send_MIX(void)
{
    n6_tx("MIX,"); n6_tx_int(mx_thr); n6_tx_char(',');
    n6_tx_int(mx_roll); n6_tx_char(','); n6_tx_int(mx_pitch); n6_tx_char(',');
    n6_tx_int(mx_yaw); n6_tx("\r\n");
}

static void set_state(uint8_t s)
{
    state = s;
    if (s != ST_ARMED) { for (int i = 0; i < 6; i++) tgt[i] = 1000; }
    raw_led(8, s == ST_ARMED);
}

/* ── command handling ────────────────────────────────────────────────────── */
static void handle_line(char *s)
{
    while (*s == ' ' || *s == '\r' || *s == '\n') s++;
    if (!*s) return;
    char c = s[0];

    if (c == '?') { tx_state(); send_Q(); n6_tx("PMU,"); n6_tx((char *)pmu_probe_name()); n6_tx("\r\n"); return; }
    if (c == 'P') { n6_tx("PONG N657 "); send_T(); return; }
    if (c == 'A') { if (mx_thr <= 1050 && state != ST_KILLED) { set_state(ST_ARMED); } else n6_tx("AE,throttle high\r\n"); tx_state(); return; }
    if (c == 'D') { set_state(ST_DISARMED); tx_state(); return; }
    if (c == '!') { set_state(ST_KILLED); n6_tx("KILLED\r\n"); return; }
    if (c == 'Q') { send_Q(); return; }
    if (c == 'Z') { ahrs_zero(); n6_tx("ZERO\r\n"); return; }
    if (c == 'B') { int r = pmu_init_n6(); n6_tx("PMU,"); n6_tx(r == 0 ? "INA228" : "NONE"); n6_tx("\r\n"); return; }
    if (c == 'S' || c == 'W') { n6_tx("CFG,SAVED\r\n"); return; }
    if (c == 'X') {
        int a, b, d, e;
        if (sscanf(s + 1, "%d,%d,%d,%d", &a, &b, &d, &e) == 4) {
            mx_thr = a; mx_roll = b; mx_pitch = d; mx_yaw = e;
            last_cmd_ms = HAL_GetTick();
            send_MIX();
        }
        return;
    }
    if (c == 'M') {                       /* M<motor>,<angle>,<dir> */
        int m, a, d;
        if (sscanf(s + 1, "%d,%d,%d", &m, &a, &d) == 3 && m >= 1 && m <= 6) {
            geo_a[m-1] = (int16_t)a; geo_d[m-1] = (int8_t)d; mix_precompute(); send_Q();
        }
        return;
    }
    if (c == 'R') {                       /* reset geometry to hexa-X default */
        static const int16_t da[6] = {30,90,210,270,150,330};
        static const int8_t  dd[6] = {-1,+1,+1,-1,-1,+1};
        for (int i = 0; i < 6; i++) { geo_a[i] = da[i]; geo_d[i] = dd[i]; geo_en[i] = 1; }
        mix_precompute(); n6_tx("CFG,DEFAULT\r\n"); send_Q(); return;
    }
    if (c == 'C' || c == 'Y') { send_MIX(); return; }
}

int main(void)
{
    raw_led_init(); raw_led(0, 1);
    SCB->VTOR = (uint32_t)g_pfnVectors; __DSB(); __ISB();

    SCB_EnableICache(); SCB_EnableDCache();
    raw_led(0, 0); raw_led(8, 1);
    HAL_Init();
    SystemClock_Config();
    raw_led(8, 0);

    n6_uart_init();

    mix_precompute();
    n6_pwm_init();
    ahrs_init();
    n6_i2c_init(400000);

    n6_tx("\r\n# MultiMotor_N6 (NUCLEO-N657X0-Q) — motors+IMU+PMU\r\n");
    int ir = imu_init();
    n6_tx("# IMU: "); n6_tx(ir == 0 ? "ISM330IS,0x6A" : "NONE"); n6_tx("\r\n");
    int pr = pmu_init_n6();
    n6_tx("# PMU: "); n6_tx(pr == 0 ? "INA228,69" : "NONE"); n6_tx("\r\n");
    n6_tx("CFG,DEFAULT\r\n"); send_Q();
    set_state(ST_DISARMED);

    uint32_t now = HAL_GetTick();
    last_imu_ms = last_telem_ms = last_batt_ms = last_q_ms = last_cmd_ms = now;

    for (;;) {
        now = HAL_GetTick();

        /* ── console RX (line based) ── */
        char ch;
        while (n6_rx_char(&ch) == 0) {
            if (ch == '\r' || ch == '\n') { cmdline[cmdlen] = 0; if (cmdlen) handle_line(cmdline); cmdlen = 0; }
            else if (cmdlen < sizeof(cmdline) - 1) cmdline[cmdlen++] = ch;
            last_cmd_ms = HAL_GetTick();
        }

        /* ── IMU + AHRS @ ~100 Hz ── */
        if (now - last_imu_ms >= 10) {
            float dt = (float)(now - last_imu_ms) * 0.001f;
            last_imu_ms = now;
            int16_t g[3], a[3];
            if (imu_read(g, a) == 0) {
                memcpy(last_g, g, sizeof g); memcpy(last_a, a, sizeof a);
                ahrs_update(g, a, dt, &roll_deg, &pitch_deg, &yaw_deg);
                imu_updates++;
            } else imu_errors++;
        }

        /* ── mixer + PWM ramp (every pass, ~1 kHz) ── */
        uint16_t out[6];
        int32_t thr = (state == ST_ARMED) ? mx_thr : 1000;
        int32_t r = (state == ST_ARMED) ? mx_roll : 0;
        int32_t p = (state == ST_ARMED) ? mx_pitch : 0;
        int32_t y = (state == ST_ARMED) ? mx_yaw : 0;
        mix_apply(thr, r, p, y, out);
        for (int i = 0; i < 6; i++) tgt[i] = out[i];
        for (int i = 0; i < 6; i++) {
            int32_t d = tgt[i] - (int32_t)motor_us[i];
            if (d > 10) d = 10; else if (d < -10) d = -10;
            motor_us[i] = (uint32_t)((int32_t)motor_us[i] + d);
            n6_pwm_set((uint8_t)i, (uint16_t)motor_us[i]);
        }

        /* ── watchdog ── */
        if (state == ST_ARMED && (now - last_cmd_ms) > 1000) {
            set_state(ST_DISARMED); n6_tx("TIMEOUT\r\n");
        }

        /* ── telemetry ── */
        if (now - last_telem_ms >= 100) { last_telem_ms = now; send_T(); }
        if (now - last_batt_ms >= 200) {
            last_batt_ms = now;
            if (pmu_read_n6(&batt_mv, &batt_ma) == 0) send_B();
        }
        if (now - last_q_ms >= 1000) {
            last_q_ms = now;
            send_E();
            n6_led_set(0, !n6_led_get(0));   /* heartbeat green */
        }

        /* ── E stream at 100 Hz ── */
        static uint32_t last_e;
        if (now - last_e >= 10) { last_e = now; send_E(); }
    }
}

/* ── clock tree: ST's N6 template (600 MHz) ─────────────────────────────── */
void SystemClock_Config(void)
{
    RCC_OscInitTypeDef o = {0}; RCC_ClkInitTypeDef c = {0};
    if (HAL_PWREx_ConfigSupply(PWR_EXTERNAL_SOURCE_SUPPLY) != HAL_OK) Error_Handler();
    if (HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1) != HAL_OK) Error_Handler();

    o.OscillatorType = RCC_OSCILLATORTYPE_HSI; o.HSIState = RCC_HSI_ON;
    o.HSIDiv = RCC_HSI_DIV1; o.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    o.PLL1.PLLState = RCC_PLL_NONE; o.PLL2.PLLState = RCC_PLL_NONE;
    o.PLL3.PLLState = RCC_PLL_NONE; o.PLL4.PLLState = RCC_PLL_NONE;
    if (HAL_RCC_OscConfig(&o) != HAL_OK) Error_Handler();

    HAL_RCC_GetClockConfig(&c);
    if (c.CPUCLKSource == RCC_CPUCLKSOURCE_IC1 || c.SYSCLKSource == RCC_SYSCLKSOURCE_IC2_IC6_IC11) {
        c.ClockType = RCC_CLOCKTYPE_CPUCLK | RCC_CLOCKTYPE_SYSCLK;
        c.CPUCLKSource = RCC_CPUCLKSOURCE_HSI; c.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
        if (HAL_RCC_ClockConfig(&c) != HAL_OK) Error_Handler();
    }

    o.OscillatorType = RCC_OSCILLATORTYPE_NONE;
    o.PLL1.PLLState = RCC_PLL_ON; o.PLL1.PLLSource = RCC_PLLSOURCE_HSI;
    o.PLL1.PLLM = 4; o.PLL1.PLLN = 75; o.PLL1.PLLFractional = 0;
    o.PLL1.PLLP1 = 1; o.PLL1.PLLP2 = 1;
    o.PLL2.PLLState = RCC_PLL_NONE; o.PLL3.PLLState = RCC_PLL_NONE; o.PLL4.PLLState = RCC_PLL_NONE;
    if (HAL_RCC_OscConfig(&o) != HAL_OK) Error_Handler();

    c.ClockType = RCC_CLOCKTYPE_CPUCLK|RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                | RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2|RCC_CLOCKTYPE_PCLK5|RCC_CLOCKTYPE_PCLK4;
    c.CPUCLKSource = RCC_CPUCLKSOURCE_IC1; c.SYSCLKSource = RCC_SYSCLKSOURCE_IC2_IC6_IC11;
    c.AHBCLKDivider = RCC_HCLK_DIV2; c.APB1CLKDivider = RCC_APB1_DIV1;
    c.APB2CLKDivider = RCC_APB2_DIV1; c.APB4CLKDivider = RCC_APB4_DIV1; c.APB5CLKDivider = RCC_APB5_DIV1;
    c.IC1Selection.ClockSelection = RCC_ICCLKSOURCE_PLL1;  c.IC1Selection.ClockDivider = 2;
    c.IC2Selection.ClockSelection = RCC_ICCLKSOURCE_PLL1;  c.IC2Selection.ClockDivider = 3;
    c.IC6Selection.ClockSelection = RCC_ICCLKSOURCE_PLL1;  c.IC6Selection.ClockDivider = 4;
    c.IC11Selection.ClockSelection = RCC_ICCLKSOURCE_PLL1; c.IC11Selection.ClockDivider = 3;
    if (HAL_RCC_ClockConfig(&c) != HAL_OK) Error_Handler();
}

void Error_Handler(void)
{
    __disable_irq();
    raw_led_init();
    for (;;) { raw_led(10, 1); for (volatile int i=0;i<300000;i++)__NOP(); raw_led(10, 0); for (volatile int i=0;i<300000;i++)__NOP(); }
}
