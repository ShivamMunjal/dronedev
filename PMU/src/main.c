/*
 * main.c - Holybro PM02D battery telemetry on a Nucleo-F401RE.
 *
 *   I2C1 : PB8 = SCL, PB9 = SDA  ->  PM02D digital power module
 *   USART2 : PA2/PA3 (ST-Link VCP), 115200 8N1  ->  telemetry
 *
 * Output is CSV so it can be piped straight into a plotter:
 *   t_ms,V_V,I_A,P_W,T_C,mAh,Wh
 */
#include "stm32f4xx.h"
#include "board.h"
#include "system.h"
#include "uart.h"
#include "i2c.h"
#include "ina2xx.h"

#define REOPEN_AFTER_ERRORS  10u

static ina_ctx_t  s_ctx;
static float      s_charge_mah;
static float      s_energy_wh;
static uint32_t   s_errors;
static uint32_t   s_samples;

static void print_csv_header(void)
{
    uart_puts("\n# t_ms,V_V,I_A,P_W,T_C,mAh,Wh\n");
}

static void print_help(void)
{
    uart_puts("# commands: i = re-print info/header, z = zero mAh/Wh counters,"
              " ? = this help\n");
}

/* Human readable configuration banner, printed once at boot */
static void print_banner(void)
{
    uart_puts("\n\n========================================================\n");
    uart_puts("  Holybro PM02D battery telemetry  -  STM32F401RE\n");
    uart_puts("========================================================\n");
    uart_puts("  SCL/SDA : PB8 / PB9 (I2C1 @ ");
    uart_print_uint(I2C_SPEED_HZ / 1000u);
    uart_puts(" kHz)\n  Console : USART2 @ ");
    uart_print_uint(CONSOLE_BAUD);
    uart_puts(" 8N1 (ST-Link VCP)\n  Shunt   : ");
    uart_print_fixed((int32_t)R_SHUNT_UOHM, 3);
    uart_puts(" mOhm\n");
}

/* Scan 0x08..0x77 and report every address that ACKs */
static void i2c_scan(void)
{
    uint32_t found = 0;

    uart_puts("\n[I2C bus scan]\n");
    for (uint8_t a = 0x08u; a < 0x78u; a++) {
        if (i2c_ping(a) == 0) {
            uart_puts("  device ACK at 0x");
            uart_print_hex8(a);
            uart_puts("\n");
            found++;
        }
    }
    if (found == 0u) {
        uart_puts("  no devices found - check wiring, GND and I2C pull-ups\n");
    }
}

/* Identify + configure the monitor. Returns 0 when ready to sample. */
static int connect_monitor(void)
{
    if (ina_open(&s_ctx) != 0) {
        uart_puts("\n[ERROR] No INA226/INA228 power monitor detected.\n");
        uart_puts("        HV PM02D = INA228 @ 0x45, LV PM02D = INA226 @ 0x41.\n");
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
    delay_ms(100);            /* let the first conversion finish */
    ina_dump(&s_ctx);
    uart_puts("  -> monitor configured OK\n");
    return 0;
}

int main(void)
{
    system_clock_init();
    uart_init();
    i2c_init();

    /* Give the host time to attach to the VCP before the banner is emitted. */
    delay_ms(1500);

    print_banner();
    i2c_scan();

    /* keep trying so the firmware still works if the module is plugged in later */
    while (connect_monitor() != 0) {
        delay_ms(1000);
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
                s_charge_mah = 0.0f;
                s_energy_wh  = 0.0f;
                uart_puts("# counters zeroed\n");
            } else if (c == '?' || c == 'h' || c == 'H') {
                print_help();
            }
        }

        if (ina_read(&s_ctx, &s) == 0) {
            const uint32_t now = system_millis();
            const uint32_t dt_ms = now - last_sample;
            last_sample = now;

            /* coulomb / energy counting */
            const float v     = (float)s.vbus_uv / 1000000.0f;
            const float i     = (float)s.current_ua / 1000000.0f;
            const float dt_s  = (float)dt_ms / 1000.0f;
            s_charge_mah += i * dt_s * (1000.0f / 3600.0f);
            s_energy_wh  += v * i * dt_s / 3600.0f;
            s_samples++;

            if ((now - last_print) >= PRINT_PERIOD_MS) {
                last_print = now;

                uart_print_uint(now);
                uart_putc(',');
                uart_print_fixed(s.vbus_uv / 1000, 3);      /* V  */
                uart_putc(',');
                uart_print_fixed(s.current_ua / 1000, 3);   /* A  */
                uart_putc(',');
                uart_print_fixed(s.power_mw, 3);            /* W  */
                uart_putc(',');
                if (s.temp_mc == INT32_MIN) {
                    uart_puts("n/a");
                } else {
                    uart_print_fixed(s.temp_mc, 3);         /* C  */
                }
                uart_putc(',');
                uart_print_float(s_charge_mah, 2);          /* mAh */
                uart_putc(',');
                uart_print_float(s_energy_wh, 3);           /* Wh  */
                uart_putc('\n');
            }

        } else {
            s_errors++;

            if ((s_errors % REOPEN_AFTER_ERRORS) == 0u) {
                uart_puts("# I2C read failed (err ");
                uart_print_uint(s_errors);
                uart_puts("), re-initialising monitor\n");
                i2c_init();
                (void)connect_monitor();
                print_csv_header();
            }
        }

        delay_ms(SAMPLE_PERIOD_MS);
    }
}
