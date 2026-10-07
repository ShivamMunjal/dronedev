/**
 * pmu.c — PM02D battery telemetry
 *
 * Current is derived from Vshunt/Rshunt inside the driver rather than from the
 * chip's CURRENT register, so it stays correct independently of calibration.
 * The coulomb/energy counters integrate the *microamp* value (not the rounded
 * milliamp one shown in telemetry), so mAh/Wh stay accurate at low currents.
 *
 * Absent / disconnected module: probing is bounded (every I2C wait has a
 * timeout) and if the module stops answering the layer stops polling it after
 * PMU_MAX_CONSECUTIVE_ERRORS, so a missing or unplugged PMU costs the mixer
 * and the control loop nothing. Send `B` to re-probe.
 */
#include <stdint.h>
#include "pmu.h"
#include "pmu_config.h"
#include "i2c.h"
#include "ina2xx.h"

#define PMU_MAX_CONSECUTIVE_ERRORS 10

static ina_ctx_t   s_ctx;
static pmu_data_t  s_pmu;
static uint8_t     s_online;          /* 0 = do not poll the bus */
static uint32_t    s_consec_errors;

/* Accumulators in uA*ms and mW*ms; converted to uAh / uWh on read:
 *   1 uAh = 3.6e6 uA*ms      1 uWh = 3600 mW*ms          */
static int64_t     s_acc_uams;
static int64_t     s_acc_mwms;

#define UAMS_PER_UAH   3600000LL
#define MWMS_PER_UWH   3600LL

static void snapshot_publish(void)
{
    s_pmu.chip       = (uint8_t)s_ctx.chip;
    s_pmu.addr       = s_ctx.addr;
    s_pmu.charge_uah = s_acc_uams / UAMS_PER_UAH;
    s_pmu.energy_uwh = s_acc_mwms / MWMS_PER_UWH;
}

int pmu_init(void)
{
    const uint32_t candidates[2] = { I2C_AF, I2C_AF_ALT };

    s_pmu.chip   = INA_CHIP_NONE;
    s_pmu.errors = 0;
    s_pmu.samples = 0;
    s_online = 0;
    s_consec_errors = 0;

    for (int c = 0; c < 2; c++) {
        i2c_init_with_af(candidates[c]);

        /* Retry a few times: the module may still be powering up. */
        for (int attempt = 0; attempt < 3; attempt++) {
            if (ina_open(&s_ctx) == 0) {
                s_pmu.af = (uint8_t)candidates[c];
                s_online = 1;
                snapshot_publish();
                return 0;
            }
        }
    }

    snapshot_publish();
    return -1;
}

int pmu_read(uint32_t dt_ms)
{
    ina_sample_t s;

    if (!s_online || s_ctx.chip == INA_CHIP_NONE) {
        return -1;                    /* no I2C traffic, no cost */
    }

    if (ina_read(&s_ctx, &s) != 0) {
        s_pmu.errors++;
        if (++s_consec_errors >= PMU_MAX_CONSECUTIVE_ERRORS) {
            /* Module went away mid-run: stop hammering the bus so the mixer
             * and control loop keep their timing. `B` re-probes. */
            s_online = 0;
            s_ctx.chip = INA_CHIP_NONE;
            s_pmu.chip = INA_CHIP_NONE;
        }
        return -1;
    }

    s_consec_errors = 0;
    s_pmu.vbus_mv    = s.vbus_uv / 1000;
    s_pmu.current_ma = s.current_ua / 1000;
    s_pmu.power_mw   = s.power_mw;
    s_pmu.temp_mc    = s.temp_mc;
    s_pmu.samples++;

    /* counters use full microamp resolution */
    s_acc_uams += (int64_t)s.current_ua * (int64_t)dt_ms;
    s_acc_mwms += (int64_t)s.power_mw   * (int64_t)dt_ms;

    snapshot_publish();
    return 0;
}

const pmu_data_t *pmu_data(void)
{
    return &s_pmu;
}

void pmu_zero_counters(void)
{
    s_acc_uams = 0;
    s_acc_mwms = 0;
    snapshot_publish();
}

int pmu_is_online(void)
{
    return s_online != 0;
}
