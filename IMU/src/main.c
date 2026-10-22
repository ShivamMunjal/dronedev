/*
 * IMU raw-data reader for NUCLEO-C092RC + STEVAL-MKI230KA (ISM330IS).
 *
 * Purpose: get RAW inertial data off the sensor and onto the Mac with nothing
 * in between. No MEMS Studio, no ST tooling, no closed protocol - just the
 * MCU reading registers over I2C and printing CSV on the ST-Link VCP.
 *
 * Why not read the MKI109V3 board directly? Its firmware only answers ST's
 * closed binary protocol (MEMS Studio), it has no ST-Link and ST ships no
 * datalog firmware for it, so the shortest path to raw data is to take the
 * DIL24 adapter off that board and wire it to this MCU - which is where it has
 * to end up anyway.
 *
 * Output (all lines are CSV; "#" lines are comments to be skipped):
 *   raw    :  I,<t_ms>,<gx>,<gy>,<gz>,<ax>,<ay>,<az>          counts (int16)
 *   scaled :  S,<t_ms>,<gx>,<gy>,<gz>,<ax>,<ay>,<az>          mdps / mg
 *
 * Commands (single letter, terminated by newline):
 *   ?        status: WHO_AM_I, address, ODR/FS, sensitivity, error count
 *   i        rescan the I2C bus and re-probe the IMU
 *   r        stream raw counts      (default)
 *   s        stream scaled units
 *   x        stop streaming
 *   z        zero the gyro (averages GYRO_ZERO_SAMPLES samples, stores bias)
 *   c        clear the gyro bias
 *   t        single sample + die temperature
 *   O<a>,<g> set ODR codes    e.g. O6,6   (416 Hz both)
 *   F<a>,<g> set full scale   e.g. F2,1   (+-4 g, +-500 dps)
 *
 * MCU: Cortex-M0+ @48 MHz, no FPU -> every conversion is integer arithmetic.
 */
#include <stdint.h>

#include "board.h"
#include "system.h"
#include "uart.h"
#include "i2c.h"
#include "ism330is.h"
#include "fusion.h"
#include "motion_fx_cm0p.h"

/* Stream modes */
enum { STREAM_RAW = 0, STREAM_SCALED = 1, STREAM_FUSED = 2, STREAM_OFF = -1 };
static int s_stream = STREAM_RAW;

static int32_t s_gyro_bias[3] = { 0, 0, 0 };   /* raw LSB */
static uint32_t s_samples = 0;
static uint32_t s_errors  = 0;
static uint32_t s_last_err = 0;   /* millis of the last printed stream error */
static uint32_t s_bad = 0;                     /* samples with a torn read / NACK */

/* ── helpers ───────────────────────────────────────────────────────────── */

static void print_csv_header(void)
{
    if (s_stream == STREAM_RAW) {
        uart_puts("# I,t_ms,gx,gy,gz,ax,ay,az   (raw int16 counts, gyro bias removed)\n");
    } else if (s_stream == STREAM_FUSED) {
        uart_puts("# E,t_ms,roll_mdeg,pitch_mdeg,yaw_mdeg,gbx_mdps,gby_mdps,gbz_mdps\n");
        uart_puts("#   MotionFX 6X (accel+gyro). roll/pitch are accel-aided;\n");
        uart_puts("#   yaw is gyro-only and WILL drift - no magnetometer on ISM330IS.\n");
    } else {
        uart_puts("# S,t_ms,gx,gy,gz,ax,ay,az   (mdps, mg)\n");
    }
}

/* Print a signed value with a trailing sign-aware '+' for easy plotting */
static void print_int_field(int32_t v)
{
    uart_putc(',');
    uart_print_int(v);
}

/* ── IMU bus: candidate pin pairs ─────────────────────────────────────── */

/* Every pair the sensor could plausibly be wired to, most likely first. The
 * PMU keeps I2C1 on PB8/PB9, so I2C2 pairs lead. PA6/PA7 and PA10 are listed
 * even though they are motor pins in the hexacopter: this is the standalone
 * reader and no motors are driven, so probing them is harmless. */
static const imu_bus_cand_t s_cands[] = {
    /* Current wiring (morpho): PB10 = CN10 pin 34, PB11 = CN7 pin 37 */
    { "PB10/PB11 (AF14)                 I2C2   [morpho CN10-34 / CN7-37]",
      'B', 10u, 14u, 'B', 11u, 14u, 2u },
    /* Escape hatch: keep SDA on PB11, move only SCL to PB13 (CN10 pin 30).
     * Useful when one morpho pin is suspect - which is exactly the case when
     * PB10 fails to show an external pull-up. */
    { "PB13/PB11 (AF14)                 I2C2   [morpho CN10-30 / CN7-37]",
      'B', 13u, 14u, 'B', 11u, 14u, 2u },
    { "PB13/PB14 (AF14)                 I2C2   [morpho CN10-30 / CN10-28]",
      'B', 13u, 14u, 'B', 14u, 14u, 2u },
    { "D8/D5   PA9(AF8)  / PB4(AF14)    I2C2   [Arduino CN5-1 / CN9-6]",
      'A',  9u,  8u, 'B',  4u, 14u, 2u },
    { "D9/D5   PB3(AF13) / PB4(AF14)    I2C2   [Arduino CN5-2 / CN9-6]",
      'B',  3u, 13u, 'B',  4u, 14u, 2u },
    { "D8/D2   PA9(AF8)  / PA10(AF8)    I2C2   [Arduino CN5-1 / CN9-3]",
      'A',  9u,  8u, 'A', 10u,  8u, 2u },
    { "D12/D11 PA6(AF6)  / PA7(AF6)     I2C2   [Arduino CN5-5 / CN5-4]",
      'A',  6u,  6u, 'A',  7u,  6u, 2u },
    /* The pair that is proven to work (sensor answered here at 100 Hz). */
    { "D15/D14 PB8(AF6)  / PB9(AF6)     I2C1   [Arduino CN5-10 / CN5-9]",
      'B',  8u,  6u, 'B',  9u,  6u, 1u },
};

#define N_CANDS (sizeof(s_cands) / sizeof(s_cands[0]))

static const imu_bus_cand_t *s_bus = &s_cands[0];
static uint8_t s_af_used = 0u;      /* AF that actually worked, for reporting */

static void imu_bus_apply(const imu_bus_cand_t *c)
{
    i2c_select(c->instance);
    (void)i2c_init_on_pins2(c->scl_port, c->scl_pin, c->scl_af,
                            c->sda_port, c->sda_pin, c->sda_af);
    s_af_used = c->scl_af;
}

/* Does an ISM330IS answer WHO_AM_I == 0x22 on the bus as currently wired?
 * Checked at both addresses because SA0/SDO selects 0x6A or 0x6B. */
static int ism_answers_here(void)
{
    uint8_t v = 0u;
    if (i2c_read_reg(0x6Au, ISM_WHO_AM_I, &v, 1u) == 0 && v == ISM_ID_ISM330IS) return 0;
    if (i2c_read_reg(0x6Bu, ISM_WHO_AM_I, &v, 1u) == 0 && v == ISM_ID_ISM330IS) return 0;
    return -1;
}

/* Lock onto whichever pair the sensor actually answers on.
 *
 * The configured AF is tried first (fast, and the intended case). If that
 * fails the whole 0..15 range is swept on both pins, because an AF number read
 * out of a datasheet table by column alignment can be off and there is no point
 * making a human rewire to discover that. Sweeping only ever configures the
 * candidate pins as open-drain alternate-function outputs, so it cannot damage
 * anything, and none of the candidates are SWD pins. */
static int imu_bus_autodetect(void)
{
    for (unsigned i = 0u; i < N_CANDS; i++) {
        const imu_bus_cand_t *c = &s_cands[i];

        imu_bus_apply(c);
        if (ism_answers_here() == 0) { s_bus = c; return 0; }

        for (uint32_t af = 0u; af <= 15u; af++) {
            if (af == c->scl_af && af == c->sda_af) continue;   /* done above */
            i2c_select(c->instance);
            if (i2c_init_on_pins2(c->scl_port, c->scl_pin, af,
                                  c->sda_port, c->sda_pin, af) != 0) continue;
            if (ism_answers_here() == 0) {
                s_bus = c;
                s_af_used = (uint8_t)af;
                return 0;
            }
        }
    }
    s_bus = &s_cands[0];
    imu_bus_apply(s_bus);
    return -1;
}

/* ── I2C bus scan ──────────────────────────────────────────────────────── */

static void bus_scan(void)
{
    uart_puts("# I2C scan on ");
    uart_puts(s_bus->name);
    uart_puts(": ");
    int found = 0;
    for (uint8_t a = 0x08u; a <= 0x77u; a++) {
        if (i2c_ping(a) == 0) {
            uart_print_hex8(a);
            uart_putc(' ');
            found++;
        }
    }
    if (!found) uart_puts("(no devices answered)");
    uart_putc('\n');
}

/* ── IMU bring-up ──────────────────────────────────────────────────────── */

static int s_imu_ok = 0;

static void imu_report(uint8_t addr, uint8_t who, int rc)
{
    uart_puts("# IMU: ");
    if (rc == 0) {
        uart_puts("ISM330IS @0x");
        uart_print_hex8(addr);
        uart_puts("  WHO_AM_I=0x");
        uart_print_hex8(who);
        uart_puts(" (ok)\n");
    } else if (rc == -2) {
        uart_puts("a device answered but WHO_AM_I=0x");
        uart_print_hex8(who);
        uart_puts(" != 0x22 - not an ISM330IS, check the wiring\n");
    } else if (rc <= -3) {
        /* The chip identified itself, so power and wiring are proven good -
         * what failed is a configuration register WRITE. */
        uart_puts("chip identified itself (WHO_AM_I=0x");
        uart_print_hex8(who);
        uart_puts(") but a register WRITE failed, rc=");
        uart_print_int(rc);
        uart_puts("\n#      (rc -3 = CTRL3_C write, -4 = ODR, -5 = FS;\n");
        uart_puts("#       -2 from a write means the slave NACKed it)\n");
    } else {
        uart_puts("not found at 0x6A or 0x6B (rc=");
        uart_print_int(rc);
        uart_puts(") - check VDD/VDDIO/GND/SCL/SDA\n");
    }
}

static void imu_bring_up(void)
{
    uint8_t addr = 0u, who = 0u;
    int rc = ism_init(&addr, &who);
    imu_report(addr, who, rc);
    s_imu_ok = (rc == 0);

    if (s_imu_ok) {
        uint32_t aug, gmd;
        ism_sensitivity(&aug, &gmd);
        uart_puts("# IMU configured: accel ");
        uart_print_uint(aug);
        uart_puts(" ug/LSB, gyro ");
        uart_print_uint(gmd);
        uart_puts(" mdps/LSB\n");
        delay_ms(50);                     /* let the first samples settle */
    }
}

/* ── gyro bias ─────────────────────────────────────────────────────────── */

static void gyro_zero(void)
{
    if (!s_imu_ok) { uart_puts("# no IMU\n"); return; }

    int64_t sum[3] = { 0, 0, 0 };
    uint32_t n = 0;
    ism_sample_t s;

    uart_puts("# keep the sensor still: averaging ");
    uart_print_uint(GYRO_ZERO_SAMPLES);
    uart_puts(" samples\n");

    for (uint32_t i = 0; i < GYRO_ZERO_SAMPLES; i++) {
        if (ism_read_sample(&s) == 0) {
            sum[0] += s.gx; sum[1] += s.gy; sum[2] += s.gz;
            n++;
        }
        delay_ms(2);
    }
    if (n == 0u) { uart_puts("# gyro zero failed (no samples)\n"); return; }

    s_gyro_bias[0] = (int32_t)(sum[0] / (int64_t)n);
    s_gyro_bias[1] = (int32_t)(sum[1] / (int64_t)n);
    s_gyro_bias[2] = (int32_t)(sum[2] / (int64_t)n);

    uart_puts("# gyro bias (raw LSB): ");
    uart_print_int(s_gyro_bias[0]); uart_putc(',');
    uart_print_int(s_gyro_bias[1]); uart_putc(',');
    uart_print_int(s_gyro_bias[2]); uart_puts("\n");
}

/* ── status ────────────────────────────────────────────────────────────── */

static void status(void)
{
    uart_puts("# ---- status ----\n# IMU      : ");
    if (s_imu_ok) {
        uart_puts("ISM330IS @0x"); uart_print_hex8(ism_addr());
    } else {
        uart_puts("not detected");
    }
    uart_puts("\n# stream   : ");
    uart_puts(s_stream == STREAM_RAW ? "raw counts" : "scaled (mdps/mg)");
    uart_puts("\n# samples  : "); uart_print_uint(s_samples);
    uart_puts("  errors: ");      uart_print_uint(s_errors);
    uart_puts("  bad: ");         uart_print_uint(s_bad);
    uart_puts("\n# gyro bias: ");
    uart_print_int(s_gyro_bias[0]); uart_putc(',');
    uart_print_int(s_gyro_bias[1]); uart_putc(',');
    uart_print_int(s_gyro_bias[2]);
    uart_puts("\n");
}

/* ── streaming ─────────────────────────────────────────────────────────── */

static int32_t scale_gyro(int32_t raw)
{
    /* The active FS is what ism_sensitivity() reports, so derive the scale from
     * that instead of duplicating the FS table (one source of truth).
     * mdeg/s = raw * full_dps * 1000 / 32768, rounded. 64-bit because at
     * +-2000 dps the product overflows 32 bits. */
    uint32_t aug, gmd;
    ism_sensitivity(&aug, &gmd);
    return (int32_t)((((int64_t)raw * (int64_t)gmd) + 16384) / 32768);
}

static int32_t scale_accel(int32_t raw)
{
    /* mg = raw * full_g * 1000 / 32768, rounded */
    uint32_t aug, gmd;
    ism_sensitivity(&aug, &gmd);
    /* aug is ug/LSB; mg = raw*aug/1000 */
    return (int32_t)((((int64_t)raw * (int64_t)aug) + 500) / 1000);
}

static void emit(const ism_sample_t *s, uint32_t t_ms)
{
    int32_t gx = s->gx - s_gyro_bias[0];
    int32_t gy = s->gy - s_gyro_bias[1];
    int32_t gz = s->gz - s_gyro_bias[2];

    if (s_stream == STREAM_FUSED) {
        /* Attitude line. 'E' for Euler, angles in milli-degrees so the control
         * path never has to parse a float. Yaw is gyro-only and drifts - see
         * fusion.c. */
        static uint32_t prev_ms = 0u;
        static int have_prev = 0;
        float dt = have_prev ? (float)(t_ms - prev_ms) / 1000.0f : 0.01f;
        prev_ms = t_ms;
        have_prev = 1;
        if (dt <= 0.0f || dt > 0.5f) dt = 0.01f;

        /* Feed the fused path bias-free gyro, but leave the raw stream alone. */
        ism_sample_t b = *s;
        b.gx = (int16_t)gx; b.gy = (int16_t)gy; b.gz = (int16_t)gz;

        fusion_euler_t e;
        if (fusion_step(&b, dt, &e) != 0) {
            return;
        }
        uart_putc('E');
        print_int_field((int32_t)t_ms);
        print_int_field(e.roll_mdeg);
        print_int_field(e.pitch_mdeg);
        print_int_field(e.yaw_mdeg);
        print_int_field(e.gbias_mdps[0]);
        print_int_field(e.gbias_mdps[1]);
        print_int_field(e.gbias_mdps[2]);
        uart_puts("\r\n");
        return;
    }

    if (s_stream == STREAM_RAW) {
        uart_putc('I');
        print_int_field((int32_t)t_ms);
        print_int_field(gx); print_int_field(gy); print_int_field(gz);
        print_int_field(s->ax); print_int_field(s->ay); print_int_field(s->az);
    } else {
        uart_putc('S');
        print_int_field((int32_t)t_ms);
        print_int_field(scale_gyro(gx));
        print_int_field(scale_gyro(gy));
        print_int_field(scale_gyro(gz));
        print_int_field(scale_accel(s->ax));
        print_int_field(scale_accel(s->ay));
        print_int_field(scale_accel(s->az));
    }
    uart_puts("\r\n");
}

/* ── pin probe: find SCL/SDA when the adapter's pinout is unknown ─────── */

/* Parse "B6" -> ('B', 6). Accepts upper or lower case port letter. */
static int parse_pin(const char **p, char *port, uint8_t *pin)
{
    char c = *(*p)++;
    if (c >= 'a' && c <= 'f') c = (char)(c - 'a' + 'A');
    if (c < 'A' || c > 'F') return -1;
    *port = c;
    uint32_t v = 0; int n = 0;
    while (**p >= '0' && **p <= '9') { v = v * 10u + (uint32_t)(**p - '0'); (*p)++; n++; }
    if (n == 0 || v > 15u) return -1;
    *pin = (uint8_t)v;
    return 0;
}

static void probe_pins(const char *spec)
{
    char sc, dc; uint8_t sp = 0, dp = 0;
    const char *p = spec;

    if (parse_pin(&p, &sc, &sp) != 0 || *p++ != ',' || parse_pin(&p, &dc, &dp) != 0) {
        uart_puts("# usage: p<scl>,<sda>   e.g. pB6,B7\n");
        uart_puts("#   ONLY pass pins confirmed to be signals, never VDD/GND\n");
        return;
    }

    uart_puts("# probing I2C1 on SCL="); uart_putc(sc); uart_print_uint(sp);
    uart_puts(" SDA="); uart_putc(dc); uart_print_uint(dp);
    uart_puts("  (sweeping AF 0..15)\n");

    int found_af = -1; uint8_t found_addr = 0; uint8_t found_inst = 1u;
    for (uint8_t inst = 1u; inst <= 2u && found_af < 0; inst++) {
        for (uint32_t af = 0; af <= 15u; af++) {
            i2c_select(inst);
            if (i2c_init_on_pins(sc, sp, dc, dp, af) != 0) continue;
            for (int i = 0; i < 2; i++) {
                uint8_t a = (i == 0) ? ISM330IS_ADDR_LO : ISM330IS_ADDR_HI;
                uint8_t who = 0;
                /* Who_AM_I is the real test - a bare address ping is not. */
                if (i2c_read_reg(a, ISM_WHO_AM_I, &who, 1u) == 0 &&
                    who == ISM_ID_ISM330IS) {
                    found_af = (int)af; found_addr = a; found_inst = inst;
                    break;
                }
            }
            if (found_af >= 0) break;
        }
    }

    if (found_af >= 0) {
        uart_puts("# FOUND ISM330IS at 0x"); uart_print_hex8(found_addr);
        uart_puts(" with AF "); uart_print_int((int32_t)found_af);
        uart_puts(" on I2C"); uart_print_uint(found_inst); uart_puts("\n");
    } else {
        uart_puts("# no ISM330IS on that pair, either I2C instance, any AF\n");
    }

    /* Restore the normal bus so streaming works again. */
    imu_bus_apply(s_bus);
    imu_bring_up();
}

/* ── electrical diagnostic ─────────────────────────────────────────────── */

/* Read every candidate pair's pins as inputs with the internal pull-up.
 *
 * Interpretation, with nothing driven by us except a ~40k pull-up:
 *   SCL=1 SDA=1  -> idle-high. Either nothing is attached, or a powered device
 *                   is attached (no device, no external pull-up: still 1).
 *   SCL=0 or SDA=0 -> something is clamping the line low. On an idle bus that
 *                   almost always means a device is wired in but UNPOWERED:
 *                   its ESD diodes conduct into its dead VDD rail. Check that
 *                   VDD *and* VDDIO are actually at 3.3 V.
 * This distinguishes "not connected" from "connected but not powered", which
 * a bus scan alone cannot do (both look like silence).
 */
static void electrical_check(void)
{
    uart_puts("# electrical check - pins as inputs with internal pull-up\n");
    uart_puts("#   1 = idle high   0 = held low (device present but unpowered?)\n");
    for (unsigned i = 0u; i < N_CANDS; i++) {
        const imu_bus_cand_t *c = &s_cands[i];
        i2c_pin_input_pullup(c->scl_port, c->scl_pin);
        i2c_pin_input_pullup(c->sda_port, c->sda_pin);
        delay_us(200);
        const int scl = i2c_pin_read(c->scl_port, c->scl_pin);
        const int sda = i2c_pin_read(c->sda_port, c->sda_pin);
        uart_puts("#   ");
        uart_puts(c->name);
        uart_puts("  SCL=");
        uart_putc(scl == 1 ? '1' : '0');
        uart_puts(" SDA=");
        uart_putc(sda == 1 ? '1' : '0');
        uart_puts((scl == 0 || sda == 0) ? "   <-- clamped low, check power\n"
                                        : "\n");
    }
    imu_bus_apply(s_bus);       /* put the I2C peripheral back on the bus */
}

/* ── locate external pull-ups ──────────────────────────────────────────── */

/* Scan every I/O as an input with the *internal pull-down* on. A pin only reads
 * 1 if something outside the MCU is pulling it up: the internal pull-down is
 * ~40k, so any external pull-up (like a 4.7k to 3V3) wins easily.
 *
 * This is how we find out which MCU pins the bus resistors were actually
 * soldered to, without trusting anybody's pin counting - if the two hits are not
 * the pins you think you wired, that is the answer.
 *
 * PA2/PA3 are skipped because they are the console UART; PA13/PA14 are skipped
 * because they are SWD. Everything scanned is only ever an input, so it cannot
 * damage or drive anything. */
static void find_pullups(void)
{
    uart_puts("# scanning all I/O for external pull-ups (internal pull-DOWN on;\n");
    uart_puts("#  a pin reading 1 has something pulling it up outside the MCU)\n");
    uart_puts("# NOTE: pins you have wired to 3V3 directly (CS, VDD) will NOT\n");
    uart_puts("#       show here - only real pull-UP resistors do.\n");

    static const char ports[4] = { 'A', 'B', 'C', 'D' };
    for (unsigned k = 0u; k < 4u; k++) {
        const char port = ports[k];
        for (uint8_t pin = 0u; pin < 16u; pin++) {
            if (port == 'A' && (pin == 2u || pin == 3u)) continue;    /* UART    */
            if (port == 'A' && (pin == 13u || pin == 14u)) continue;  /* SWD     */

            i2c_pin_input(port, pin, 2u);        /* input, pull-DOWN */
            delay_us(300);
            if (i2c_pin_read(port, pin) == 1) {
                uart_puts("#   pull-up detected on P");
                uart_putc(port);
                uart_print_uint(pin);
                uart_putc('\n');
            }
        }
    }
    uart_puts("# scan done. Expect exactly the SCL and SDA pins of each bus in use,\n");
    uart_puts("# plus any onboard pull-ups (NRST/BOOT0 etc.).\n");

    /* Capacitance probe. A pin with a resistor but NO wire rises almost at
     * once; a pin really wired to the adapter rises slowly through its 330 pF.
     * Comparing pins is the point - the absolute numbers are not calibrated, so
     * look for the outlier, not the value: a wired pin reads far higher than
     * an unwired one on this board. */
    uart_puts("# rise-time probe (authority only as a comparison between pins):\n");
    static const struct { char port; uint8_t pin; } probe[] = {
        { 'B',  8u }, { 'B',  9u }, { 'B', 10u }, { 'B', 11u },
    };
    for (unsigned i = 0u; i < sizeof(probe) / sizeof(probe[0]); i++) {
        const uint32_t t = i2c_pin_rise_ticks(probe[i].port, probe[i].pin);
        uart_puts("#   P"); uart_putc(probe[i].port); uart_print_uint(probe[i].pin);
        uart_puts(" rise="); uart_print_uint(t);
        uart_puts(t > 25u ? "   <- wire/capacitance present\n"
                          : "   <- looks bare (resistor but no wire)\n");
    }

    imu_bus_apply(s_bus);       /* put the I2C peripheral back on the bus */
}

/* ── command handling ──────────────────────────────────────────────────── */

/* Parse up to n comma-separated unsigned ints from s. Returns how many were
 * read. Used by the O/F commands: "O6,6" -> {6,6}. */
static int parse_csv_u(const char *s, uint32_t *out, int n)
{
    int cnt = 0;
    while (cnt < n && *s) {
        while (*s == ' ' || *s == ',') s++;
        if (*s < '0' || *s > '9') break;
        uint32_t v = 0;
        while (*s >= '0' && *s <= '9') { v = v * 10u + (uint32_t)(*s - '0'); s++; }
        out[cnt++] = v;
    }
    return cnt;
}

/* One complete command line (newline already stripped). */
static void process_line(char *line)
{
    if (!line[0]) return;

    switch (line[0]) {
    case '?': status(); break;
    case 'i': bus_scan(); imu_bring_up(); print_csv_header(); break;
    case 'p': case 'P': probe_pins(line + 1); print_csv_header(); break;
    case 'b': case 'B':          /* re-run the pin-pair search */
        if (imu_bus_autodetect() == 0) {
            uart_puts("# BUS: sensor answered on ");
            uart_puts(s_bus->name);
            uart_putc('\n');
        } else {
            uart_puts("# BUS: no ISM330IS found on any known pin pair\n");
        }
        bus_scan();
        imu_bring_up();
        print_csv_header();
        break;

    case 'e': case 'E': electrical_check(); break;
    case 'L': find_pullups(); break;          /* Locate external pull-ups */

    case 'V': case 'v': {                 /* bus speed, kHz */
        uint32_t a[1];
        if (parse_csv_u(line + 1, a, 1) != 1) {
            uart_puts("# usage: V<kHz> where kHz is 100, 50, 20 or 10\n");
            uart_puts("#   if the part answers at 10 kHz but not 100 kHz, the bus\n");
            uart_puts("#   needs real pull-ups (4.7k from SDA and SCL to 3V3)\n");
            break;
        }
        uint32_t t = 0u;
        if      (a[0] == 100u) t = 0xB4201113u;   /* SCLH=17  SCLL=19 -> 105 kHz */
        else if (a[0] ==  50u) t = 0xB4201313u;   /* SCLH=19  SCLL=19 ->  50 kHz */
        else if (a[0] ==  20u) t = 0xB4206363u;   /* SCLH=99  SCLL=99 ->  20 kHz */
        else if (a[0] ==  10u) t = 0xB420C7C7u;   /* SCLH=199 SCLL=199 -> 10 kHz */
        if (!t) { uart_puts("# speeds available: 100, 50, 20, 10 kHz\n"); break; }
        i2c_set_timing(t);
        uart_puts("# I2C bus set to ");
        uart_print_uint(a[0]);
        uart_puts(" kHz\n");
        bus_scan();
        break;
    }

    case 'W': case 'w': {           /* write-test: W<reg>,<value> then read back */
        uint32_t a[2];
        if (parse_csv_u(line + 1, a, 2) != 2) {
            uart_puts("# usage: W<reg>,<value>  writes an 8-bit register and reads it back\n");
            break;
        }
        const uint8_t reg = (uint8_t)a[0], val = (uint8_t)a[1];
        int wrc = i2c_write_reg8(0x6Au, reg, val);
        uint8_t rb = 0u;
        int rrc = i2c_read_reg(0x6Au, reg, &rb, 1u);
        uart_puts("# write reg 0x"); uart_print_hex8(reg);
        uart_puts(" <- 0x"); uart_print_hex8(val);
        uart_puts("  write_rc="); uart_print_int(wrc);
        uart_puts("  read_rc=");  uart_print_int(rrc);
        uart_puts("  readback=0x"); uart_print_hex8(rb);
        uart_putc('\n');
        break;
    }

    case 'r': s_stream = STREAM_RAW;    print_csv_header(); break;
    case 's': s_stream = STREAM_SCALED; print_csv_header(); break;
    case 'a': case 'A': s_stream = STREAM_FUSED; fusion_init(); print_csv_header(); break;
    case 'x': s_stream = STREAM_OFF; uart_puts("# streaming stopped (r, s or a to resume)\n"); break;

    case 'z': gyro_zero(); break;
    case 'c': s_gyro_bias[0] = s_gyro_bias[1] = s_gyro_bias[2] = 0;
              uart_puts("# gyro bias cleared\n"); break;

    case 't': {
        ism_sample_t s;
        if (ism_read_sample(&s) == 0) {
            uart_puts("# temp ");
            uart_print_int(ism_temp_mdegC(s.temp_raw));
            uart_puts(" mdegC\n");
        } else {
            uart_puts("# read failed\n");
        }
        break;
    }

    case 'O': case 'o': {
        uint32_t a[2];
        if (parse_csv_u(line + 1, a, 2) != 2) {
            uart_puts("# usage: O<accel_odr>,<gyro_odr>  codes 0=off 1=12.5 2=26 "
                      "3=52 4=104 5=208 6=416 7=833 8=1667 9=3333 10=6667 Hz\n");
            break;
        }
        if (ism_set_odr((uint8_t)a[0], (uint8_t)a[1]) != 0) {
            uart_puts("# ODR set failed (out of range or I2C error)\n");
        } else {
            uart_puts("# ODR set\n");
            print_csv_header();
        }
        break;
    }

    case 'F': case 'f': {
        uint32_t a[2];
        if (parse_csv_u(line + 1, a, 2) != 2) {
            uart_puts("# usage: F<accel_fs>,<gyro_fs>  accel 0=2g 1=16g 2=4g 3=8g | "
                      "gyro 0=250 1=500 2=1000 3=2000 dps\n");
            break;
        }
        if (ism_set_fs((uint8_t)a[0], (uint8_t)a[1]) != 0) {
            uart_puts("# FS set failed (out of range or I2C error)\n");
        } else {
            uint32_t aug, gmd;
            ism_sensitivity(&aug, &gmd);
            uart_puts("# FS set: accel "); uart_print_uint(aug);
            uart_puts(" ug/LSB, gyro "); uart_print_uint(gmd);
            uart_puts(" mdps/LSB\n");
        }
        break;
    }

    default:
        uart_puts("# unknown command - ? for status\n");
        break;
    }
}

/* ── MotionFX bring-up probe ───────────────────────────────────────────── */

/* Walk MotionFX's initialisation one call at a time, printing BEFORE each call,
 * once per second until the sequence completes.
 *
 * Why from the main loop and not at boot: if a library call traps, a boot-time
 * init means the console never comes up and the only symptom is silence. Run
 * from the loop, we always have the raw stream and the last printed line tells
 * us exactly which call never returned. Prints go out before the call, so the
 * message survives even if the call never returns. */
static void __attribute__((unused)) fusion_probe_task(void)
{
    static uint32_t next_ms = 0u;
    static int      done = 0;
    static int      attempts = 0;

    if (done || attempts >= 3) return;

    const uint32_t now = system_millis();
    if (next_ms && (int32_t)(now - next_ms) < 0) return;
    next_ms = now + 1000u;
    attempts++;

    uart_puts("# fx["); uart_print_uint((uint32_t)attempts); uart_puts("]: hw prepare (CRC clock)...\n");
    fusion_hw_prepare();

    uart_puts("# fx: initialize...\n");
    MotionFX_CM0P_initialize(MFX_CM0P_MCU_STM32);
    uart_puts("# fx: initialize OK\n");

    uart_puts("# fx: setOrientation...\n");
    MotionFX_CM0P_setOrientation("ENU", "ENU", "ENU");
    uart_puts("# fx: setOrientation OK\n");

    uart_puts("# fx: enable_6X...\n");
    MotionFX_CM0P_enable_6X(MFX_CM0P_ENGINE_ENABLE);
    uart_puts("# fx: enable_6X OK\n");

    uart_puts("# fx: enable_9X(off)...\n");
    MotionFX_CM0P_enable_9X(MFX_CM0P_ENGINE_DISABLE);
    uart_puts("# fx: enable_9X OK\n");

    uart_puts("# fx: enable_euler...\n");
    MotionFX_CM0P_enable_euler(MFX_CM0P_ENGINE_ENABLE);
    uart_puts("# fx: enable_euler OK\n");

    uart_puts("# fx: enable_gbias...\n");
    MotionFX_CM0P_enable_gbias(MFX_CM0P_ENGINE_ENABLE);
    uart_puts("# fx: enable_gbias OK\n");

    char ver[24];
    if (MotionFX_CM0P_GetLibVersion(ver) != 0u) {
        uart_puts("# fx: MotionFX version "); uart_puts(ver); uart_putc('\n');
    }

    uart_puts("# fx: INIT SEQUENCE COMPLETE - library is usable on this MCU\n");
    done = 1;
}

/* ── main ──────────────────────────────────────────────────────────────── */

int main(void)
{
    system_clock_init();
    uart_init();

    uart_puts("\n\n=== IMU raw reader - NUCLEO-C092RC + ISM330IS (STEVAL-MKI230A/BV5) ===\n");
    uart_puts("# data is raw sensor counts; no filtering, no fusion\n");

    if (imu_bus_autodetect() == 0) {
        uart_puts("# BUS: sensor answered on ");
        uart_puts(s_bus->name);
        uart_puts(" AF=");
        uart_print_uint(s_af_used);
        uart_putc('\n');
    } else {
        uart_puts("# BUS: no ISM330IS on any known pin pair, falling back to ");
        uart_puts(s_bus->name);
        uart_putc('\n');
        uart_puts("#      check CS is pulled HIGH to 3V3, and that SCL/SDA are on\n");
        uart_puts("#      a pair this firmware knows about (b re-runs the search)\n");
        /* Auto-run the resistor locator so a plain reset is enough to get the
         * answer - it does not depend on a typed command being received. */
        find_pullups();
    }
    bus_scan();
    imu_bring_up();

    /* NOTE: MotionFX is intentionally NOT initialised here. Doing it at boot
     * means a hang in the library stops the firmware before the console is up,
     * so all we see is silence and we cannot tell which call trapped. Instead
     * fusion_probe_task() walks the init sequence from the main loop, one call
     * at a time, printing before each - so the last line seen names the
     * offending call even if the CPU never returns from it. */

    print_csv_header();

    uint32_t next = system_millis();
    char     cmd_buf[32];
    uint8_t  cmd_len = 0;

    for (;;) {
        /* Accumulate a whole line before dispatching, so commands that take
         * arguments (O6,6 / F2,1) can be parsed. */
        int ch = uart_getc();
        while (ch >= 0) {
            if (ch == '\n' || ch == '\r') {
                cmd_buf[cmd_len] = 0;
                process_line(cmd_buf);
                cmd_len = 0;
            } else if (ch >= 32 && ch < 127) {
                if (cmd_len < sizeof(cmd_buf) - 1u) cmd_buf[cmd_len++] = (char)ch;
            }
            ch = uart_getc();
        }

        /* MotionFX is initialised lazily by the first 'a' (attitude stream),
         * which is proven safe on this MCU. The old step-by-step boot probe is
         * retired: it initialised the library a second time, and 'a' then
         * re-initialised it. */
        if (s_stream < 0) { delay_ms(5); continue; }

        /* paced stream */
        uint32_t now = system_millis();
        if ((int32_t)(now - next) >= 0) {
            next += (1000u / IMU_PRINT_HZ);

            ism_sample_t s;
            if (ism_read_sample(&s) == 0) {
                s_samples++;
                emit(&s, now);
            } else {
                s_bad++;
                s_errors++;
                /* Rate-limit the message to once a second. At 100 Hz the old
                 * counter re-printed every 20 failures forever, and that steady
                 * output is what starved the ST-Link bridge of host->device
                 * traffic, so typed commands were only sometimes delivered. */
                const uint32_t t_err = system_millis();
                if ((uint32_t)(t_err - s_last_err) >= 1000u) {
                    s_last_err = t_err;
                    uart_puts("# ERROR: no data from the IMU - check wiring, or run 'L'\n");
                }
            }
        }
    }
}
