/*
 * main.c - Holybro PM02D battery telemetry on a NUCLEO-C092RC (STM32C092RC).
 *
 *   I2C1  : PB8 = SCL, PB9 = SDA (CN10 pins 3 and 5) -> PM02D power module
 *   USART2: PA2/PA3 -> on-board ST-LINK VCP, 115200 8N1
 *
 * Output is CSV so it can be piped straight into a plotter:
 *   t_ms,V_V,I_A,P_W,T_C,mAh,Wh
 *
 * The Cortex-M0+ has no FPU, so the charge/energy accumulators are 64-bit
 * integer sums (uA*ms and mW*ms) and every value is printed as fixed point.
 */
#include "stm32c0xx.h"
#include "board.h"
#include "system.h"
#include "uart.h"
#include "i2c.h"
#include "ina2xx.h"

#define REOPEN_AFTER_ERRORS  10u

/* Accumulators: microamp-milliseconds and milliwatt-milliseconds */
#define UAMS_PER_MAH   3600000LL   /* uA*ms -> uAh*1000 */
#define MWMS_PER_WH    3600000LL   /* mW*ms -> uWh*1000 */

static ina_ctx_t s_ctx;
static uint32_t  s_af = I2C_AF;
static int64_t   s_charge_uams;
static int64_t   s_energy_mwms;
static uint32_t  s_errors;
static uint32_t  s_samples;

static void print_csv_header(void)
{
    uart_puts("\n# t_ms,V_V,I_A,P_W,T_C,mAh,Wh\n");
}

static void print_help(void)
{
    uart_puts("# commands: i = re-print info/header, z = zero mAh/Wh counters,"
              " ? = this help\n");
}

static void print_banner(void)
{
    uart_puts("\n\n========================================================\n");
    uart_puts("  Holybro PM02D battery telemetry  -  STM32C092RC\n");
    uart_puts("  (NUCLEO-C092RC, Cortex-M0+ @ 48 MHz)\n");
    uart_puts("========================================================\n");
    uart_puts("  SCL/SDA : PB8 / PB9  (CN10 pins 3 and 5, I2C1 @ ");
    uart_print_uint(I2C_SPEED_HZ / 1000u);
    uart_puts(" kHz)\n  Console : USART2 @ ");
    uart_print_uint(CONSOLE_BAUD);
    uart_puts(" 8N1 (ST-Link VCP, PA2/PA3)\n  Shunt   : ");
    uart_print_fixed((int32_t)R_SHUNT_UOHM, 3);
    uart_puts(" mOhm\n");
}

/* Scan 0x08..0x77 and report every address that ACKs */
static uint32_t i2c_scan(void)
{
    uint32_t found = 0;
    uint32_t nacks = 0;

    uart_puts("\n[I2C bus scan, AF");
    uart_print_uint(s_af);
    uart_puts("]\n");

    for (uint8_t a = 0x08u; a < 0x78u; a++) {
        const int rc = i2c_ping(a);
        if (rc == 0) {
            uart_puts("  device ACK at 0x");
            uart_print_hex8(a);
            uart_puts("\n");
            found++;
        } else if (rc == -2) {
            nacks++;   /* controller transmitted and got an answer */
        }
    }
    if (found == 0u) {
        if (nacks > 0u) {
            uart_puts("  no ACK from any address (");
            uart_print_uint(nacks);
            uart_puts(" NACKs) -> the I2C controller is transmitting,"
                      " but no target answers\n");
        } else {
            uart_puts("  no bus activity at all -> check SCL/SDA, GND and"
                      " the pin alternate function\n");
        }
    }
    return found;
}

/*
 * I2C line tester.
 *
 * Reads PB8/PB9 first with the internal pull-up (~40k) and then with the
 * internal pull-down enabled. That separates the three failure modes which all
 * look identical as "no devices found":
 *
 *   high / high : an external pull-up is present, so the module's own pull-ups
 *                 are powered -> a powered module really is on these pins
 *   high / low  : no external pull-up -> nothing connected, or the module has
 *                 no supply (its pull-ups are dead), or SCL/SDA are swapped
 *   low  / any  : a line is held low -> stuck slave, short, or wrong pin
 */
static void report_i2c_lines(void)
{
    uint32_t up, down;

    GPIOB->MODER &= ~((3u << GPIO_MODER_MODE8_Pos) | (3u << GPIO_MODER_MODE9_Pos));

    GPIOB->PUPDR = (GPIOB->PUPDR & ~((3u << GPIO_PUPDR_PUPD8_Pos) | (3u << GPIO_PUPDR_PUPD9_Pos))) |
                   (1u << GPIO_PUPDR_PUPD8_Pos) | (1u << GPIO_PUPDR_PUPD9_Pos);
    delay_us(500);
    up = GPIOB->IDR;

    GPIOB->PUPDR = (GPIOB->PUPDR & ~((3u << GPIO_PUPDR_PUPD8_Pos) | (3u << GPIO_PUPDR_PUPD9_Pos))) |
                   (2u << GPIO_PUPDR_PUPD8_Pos) | (2u << GPIO_PUPDR_PUPD9_Pos);
    delay_us(500);
    down = GPIOB->IDR;

    const int scl_up = (up   & (1u << 8)) != 0u;
    const int sda_up = (up   & (1u << 9)) != 0u;
    const int scl_dn = (down & (1u << 8)) != 0u;
    const int sda_dn = (down & (1u << 9)) != 0u;

    uart_puts("\n[I2C line check]  SCL = PB8 (CN10 pin 3),  SDA = PB9 (CN10 pin 5)\n");
    uart_puts("  internal pull-up    : SCL=");
    uart_putc(scl_up ? '1' : '0');
    uart_puts(" SDA=");
    uart_putc(sda_up ? '1' : '0');
    uart_puts("   (1/1 = bus idle high)\n");
    uart_puts("  internal pull-down  : SCL=");
    uart_putc(scl_dn ? '1' : '0');
    uart_puts(" SDA=");
    uart_putc(sda_dn ? '1' : '0');
    uart_puts("   (1 here = external pull-up present)\n");

    if (!scl_up || !sda_up) {
        uart_puts("  -> a line is held LOW: stuck slave, short, or wrong pin\n");
    } else if (scl_dn && sda_dn) {
        uart_puts("  -> external pull-ups detected: a powered device is on these pins\n");
    } else {
        uart_puts("  -> no external pull-up: module not connected, unpowered"
                  " (battery required), or SCL/SDA swapped\n");
    }

    i2c_init_with_af(s_af);   /* restore the alternate function */
}

/* Identify + configure the monitor. 0 when ready to sample. */
static int connect_monitor(void)
{
    if (ina_open(&s_ctx) != 0) {
        return -1;
    }

    uart_puts("\n[Power monitor detected]\n");
    uart_puts("  chip         = ");
    uart_puts(ina_chip_name(s_ctx.chip));
    uart_puts("  @ 0x");
    uart_print_hex8(s_ctx.addr);
    uart_puts("\n");
    uart_puts("  full scale  = ");
    uart_print_uint(s_ctx.chip == INA_CHIP_228 ? INA228_IMAX_MA / 1000u
                                               : INA226_IMAX_MA / 1000u);
    uart_puts(" A\n");
    delay_ms(100);                 /* let the first conversion finish */
    ina_dump(&s_ctx);
    uart_puts("  -> monitor configured OK\n");
    return 0;
}

int main(void)
{
    system_clock_init();
    uart_init();

    i2c_init_with_af(I2C_AF);

    /* Give the host time to attach to the VCP before the banner is emitted. */
    delay_ms(1500);

    print_banner();
    report_i2c_lines();

    /* The I2C1 pin AF on this part is AF6 (per ST's NUCLEO-C092RC examples);
     * if that yields no answer, retry on AF7 so a wrong assumption cannot
     * leave the board silently dead. */
    if (connect_monitor() != 0) {
        uart_puts("\n# no monitor on AF6, retrying on AF7\n");
        i2c_init_with_af(I2C_AF_ALT);
        if (connect_monitor() == 0) {
            s_af = I2C_AF_ALT;
        } else {
            i2c_init_with_af(I2C_AF);
        }
    }

    if (s_ctx.chip == INA_CHIP_NONE) {
        uart_puts("\n[ERROR] No INA226/INA228 power monitor detected.\n");
        uart_puts("        HV PM02D = INA228 @ 0x45, LV PM02D = INA226 @ 0x41.\n");
    }

    (void)i2c_scan();

    /* keep retrying so the firmware works if the module is plugged in later */
    while (s_ctx.chip == INA_CHIP_NONE) {
        delay_ms(2000);
        i2c_init_with_af(I2C_AF);
        if (connect_monitor() == 0) {
            (void)i2c_scan();
        }
    }

    print_csv_header();
    print_help();

    uint32_t last_sample = system_millis();
    uint32_t last_print  = last_sample;

    for (;;) {
        ina_sample_t s;

        /* interactive commands */
        for (int c = uart_getc(); c >= 0; c = uart_getc()) {
            if (c == 'i' || c == 'I') {
                print_banner();
                print_csv_header();
            } else if (c == 'z' || c == 'Z') {
                s_charge_uams = 0;
                s_energy_mwms = 0;
                uart_puts("# counters zeroed\n");
            } else if (c == '?' || c == 'h' || c == 'H') {
                print_help();
            }
        }

        if (ina_read(&s_ctx, &s) == 0) {
            const uint32_t now = system_millis();
            const uint32_t dt_ms = now - last_sample;
            last_sample = now;

            /* coulomb / energy counting in integer units */
            s_charge_uams += (int64_t)s.current_ua * (int64_t)dt_ms;
            s_energy_mwms += (int64_t)s.power_mw * (int64_t)dt_ms;
            s_samples++;

            if ((now - last_print) >= PRINT_PERIOD_MS) {
                last_print = now;

                uart_print_uint(now);
                uart_putc(',');
                uart_print_fixed(s.vbus_uv / 1000, 3);        /* V   */
                uart_putc(',');
                uart_print_fixed(s.current_ua / 1000, 3);     /* A   */
                uart_putc(',');
                uart_print_fixed(s.power_mw, 3);              /* W   */
                uart_putc(',');
                if (s.temp_mc == INT32_MIN) {
                    uart_puts("n/a");
                } else {
                    uart_print_fixed(s.temp_mc, 3);           /* C   */
                }
                uart_putc(',');
                uart_print_fixed64(s_charge_uams / UAMS_PER_MAH, 3);  /* mAh */
                uart_putc(',');
                uart_print_fixed64(s_energy_mwms / MWMS_PER_WH, 3);   /* Wh  */
                uart_putc('\n');
            }

        } else {
            s_errors++;

            if ((s_errors % REOPEN_AFTER_ERRORS) == 0u) {
                uart_puts("# I2C read failed (err ");
                uart_print_uint(s_errors);
                uart_puts("), re-initialising monitor\n");
                i2c_bus_recover();
                if (connect_monitor() != 0) {
                    s_ctx.chip = INA_CHIP_NONE;
                }
                print_csv_header();
            }
        }

        delay_ms(SAMPLE_PERIOD_MS);
    }
}
