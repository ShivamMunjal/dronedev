/*
 * ina2xx.c - Texas Instruments INA226 / INA228 digital power monitor driver.
 *
 * Written for the Holybro PM02D power module family, which is a 0.5 mOhm shunt
 * plus a TI monitor behind I2C:
 *
 *   PM02D  "LV"  6S     : INA226 @ 0x41, +/-81.92 mV  -> 163.84 A full scale
 *   PM02D  "HV"  2S-12S : INA228 @ 0x45, +/-163.84 mV -> 327.68 A full scale
 *
 * The current is derived from the shunt-voltage register (Vshunt / Rshunt)
 * instead of the chip's CURRENT register, because that is exact and does not
 * depend on the calibration register being right. The chip's own CURRENT
 * register is read too and reported for cross-checking.
 *
 * Register/scaling reference: TI INA226 & INA228 datasheets, cross-checked
 * against the PX4-Autopilot ina226/ina228 drivers.
 */
#include "stm32c0xx.h"
#include "pmu_config.h"
#include "i2c.h"

static void ina_delay_ms(uint32_t ms)
{
    while (ms-- != 0u) {
        for (volatile uint32_t n = 12000u; n != 0u; n--) {
        }
    }
}
#include "ina2xx.h"


/* ---- register maps ---- */
/* INA226 (16-bit registers, big endian) */
#define R226_CONFIG      0x00
#define R226_SHUNTV      0x01
#define R226_BUSV        0x02
#define R226_POWER       0x03
#define R226_CURRENT     0x04
#define R226_CALIB       0x05
#define R226_MFG_ID      0xFE
#define R226_DIE_ID      0xFF

/* INA228 (16-bit config, 24-bit measurement registers) */
#define R228_CONFIG      0x00
#define R228_ADCCONFIG   0x01
#define R228_SHUNTCAL    0x02
#define R228_VSHUNT      0x04
#define R228_VBUS        0x05
#define R228_DIETEMP     0x06
#define R228_CURRENT     0x07
#define R228_POWER       0x08
#define R228_MFG_ID      0x3E
#define R228_DEV_ID      0x3F

#define TI_MFG_ID        0x5449u   /* "TI" */
#define DIE_226          0x226u
#define DIE_228          0x228u

/* CONFIG (0x00) for INA228: RST bit + ADCRANGE (+/-163.84 mV) */
#define R228_CONFIG_RST        0x8000u
#define R228_ADCRANGE_HIGH     0x0000u   /* +/-163.84 mV -> 327.68 A @0.5mOhm */

/* ADC_CONFIG (0x01) value: continuous temp+shunt+bus, 540 us, average 16 */
#define R228_ADC_CONFIG_VALUE  0xF922u

/* CONFIG (0x00) value for INA226: average 64, 588 us, continuous shunt+bus */
#define R226_CONFIG_VALUE      0x06DFu

/* Full-scale current used to size the calibration registers */
#define IMAX_MA_228     INA228_IMAX_MA
#define IMAX_MA_226     INA226_IMAX_MA

/* ------------------------------------------------------------------ */
/* low level register access                                          */
/* ------------------------------------------------------------------ */

static int read_u16(uint8_t addr, uint8_t reg, uint16_t *out)
{
    uint8_t b[2];
    if (i2c_read_reg(addr, reg, b, 2) != 0) {
        return -1;
    }
    *out = (uint16_t)((b[0] << 8) | b[1]);
    return 0;
}

/* Reads a 24-bit big-endian register and returns its signed 20-bit value
 * (the INA228 left-aligns 20-bit results inside 24 bits). */
static int read_s20(uint8_t addr, uint8_t reg, int32_t *out)
{
    uint8_t b[3];
    if (i2c_read_reg(addr, reg, b, 3) != 0) {
        return -1;
    }
    uint32_t raw = ((uint32_t)b[0] << 16) | ((uint32_t)b[1] << 8) | b[2];
    int32_t v = (int32_t)(raw >> 4);
    if (v & 0x80000) {          /* sign extend 20 bits */
        v -= 0x100000;
    }
    *out = v;
    return 0;
}

/* ------------------------------------------------------------------ */
/* scaling helpers (integer only - exact, no float rounding)          */
/* ------------------------------------------------------------------ */

/* INA228: VBUS LSB = 195.3125 uV = 3125/16 uV */
static int32_t vbus_uv_228(int32_t raw20)
{
    return (int32_t)(((int64_t)raw20 * 3125) / 16);
}

/* INA228: VSHUNT LSB = 312.5 nV = 625/2 nV (ADCRANGE = +/-163.84 mV) */
static int32_t vshunt_nv_228(int32_t raw20)
{
    return (int32_t)(((int64_t)raw20 * 625) / 2);
}

/* INA228: temperature LSB = 7.8125 mC = 125/16 mC */
static int32_t temp_mc_228(int16_t raw)
{
    return (int32_t)(((int64_t)raw * 125) / 16);
}

/* INA226: VBUS LSB = 1.25 mV, VSHUNT LSB = 2.5 uV */
#define VBUS_UV_226(raw)    ((int32_t)(raw) * 1250)
#define VSHUNT_NV_226(raw)  ((int32_t)(raw) * 2500)

/* I = Vshunt / Rshunt, returned in microamps */
static int32_t current_ua_from_shunt(int32_t vshunt_nv)
{
    return (int32_t)(((int64_t)vshunt_nv * 1000) / (int64_t)R_SHUNT_UOHM);
}

/* ------------------------------------------------------------------ */
/* identification                                                     */
/* ------------------------------------------------------------------ */

const char *ina_chip_name(ina_chip_t chip)
{
    switch (chip) {
    case INA_CHIP_226: return "INA226";
    case INA_CHIP_228: return "INA228";
    default:           return "none";
    }
}

static int probe_228(uint8_t addr, uint16_t *mfg, uint16_t *dev)
{
    if (read_u16(addr, R228_MFG_ID, mfg) != 0 || *mfg != TI_MFG_ID) {
        return -1;
    }
    if (read_u16(addr, R228_DEV_ID, dev) != 0 || ((*dev >> 4) & 0x0FFFu) != DIE_228) {
        return -1;
    }
    return 0;
}

static int probe_226(uint8_t addr, uint16_t *mfg, uint16_t *dev)
{
    if (read_u16(addr, R226_MFG_ID, mfg) != 0 || *mfg != TI_MFG_ID) {
        return -1;
    }
    if (read_u16(addr, R226_DIE_ID, dev) != 0 || ((*dev >> 4) & 0x0FFFu) != DIE_226) {
        return -1;
    }
    return 0;
}

/* ------------------------------------------------------------------ */
/* configuration                                                      */
/* ------------------------------------------------------------------ */

static int config_228(ina_ctx_t *ctx)
{
    /* SHUNT_CAL = 13107.2e6 * (Imax / 2^19) * Rshunt
     *           = Imax[mA] * Rshunt[uOhm] / 40000                       */
    uint32_t cal = (uint32_t)(((uint64_t)IMAX_MA_228 * R_SHUNT_UOHM) / 40000u);

    ctx->config = R228_ADCRANGE_HIGH;
    ctx->cal    = (uint16_t)cal;

    /* reset, then wait for the part to come back */
    if (i2c_write_reg16(ctx->addr, R228_CONFIG, R228_CONFIG_RST) != 0) {
        return -1;
    }
    ina_delay_ms(2);

    if (i2c_write_reg16(ctx->addr, R228_SHUNTCAL, ctx->cal) != 0) {
        return -1;
    }
    if (i2c_write_reg16(ctx->addr, R228_CONFIG, ctx->config) != 0) {
        return -1;
    }
    if (i2c_write_reg16(ctx->addr, R228_ADCCONFIG, R228_ADC_CONFIG_VALUE) != 0) {
        return -1;
    }

    /* read back for verification */
    uint16_t rb = 0;
    if (read_u16(ctx->addr, R228_ADCCONFIG, &rb) != 0 ||
        rb != R228_ADC_CONFIG_VALUE) {
        return -1;
    }
    return 0;
}

static int config_226(ina_ctx_t *ctx)
{
    /* CAL = 0.00512 / (I_lsb * Rshunt), I_lsb = Imax / 32768
     *     = 167772160000 / (Imax[mA] * Rshunt[uOhm])                 */
    uint32_t cal = (uint32_t)(167772160000ULL /
                              ((uint64_t)IMAX_MA_226 * R_SHUNT_UOHM));

    ctx->config = R226_CONFIG_VALUE;
    ctx->cal    = (uint16_t)cal;

    if (i2c_write_reg16(ctx->addr, R226_CONFIG, 0x8000u) != 0) {  /* reset */
        return -1;
    }
    ina_delay_ms(2);
    if (i2c_write_reg16(ctx->addr, R226_CALIB, ctx->cal) != 0) {
        return -1;
    }
    if (i2c_write_reg16(ctx->addr, R226_CONFIG, ctx->config) != 0) {
        return -1;
    }

    uint16_t rb = 0;
    if (read_u16(ctx->addr, R226_CONFIG, &rb) != 0 ||
        (rb & 0x0FFFu) != (ctx->config & 0x0FFFu)) {
        return -1;
    }
    return 0;
}

/* ------------------------------------------------------------------ */
/* public API                                                         */
/* ------------------------------------------------------------------ */

int ina_open(ina_ctx_t *ctx)
{
    /* HV first: that is what the "2S-12S / high voltage" PM02D uses. */
    static const uint8_t candidates[] = { INA228_ADDR, 0x44u, 0x41u, 0x40u };

    ctx->chip = INA_CHIP_NONE;

    for (uint32_t i = 0; i < sizeof(candidates); i++) {
        uint16_t mfg = 0, dev = 0;
        if (probe_228(candidates[i], &mfg, &dev) == 0) {
            ctx->chip   = INA_CHIP_228;
            ctx->addr   = candidates[i];
            ctx->mfg_id = mfg;
            ctx->dev_id = dev;
            return config_228(ctx);
        }
    }

    for (uint32_t i = 0; i < sizeof(candidates); i++) {
        uint16_t mfg = 0, dev = 0;
        if (probe_226(candidates[i], &mfg, &dev) == 0) {
            ctx->chip   = INA_CHIP_226;
            ctx->addr   = candidates[i];
            ctx->mfg_id = mfg;
            ctx->dev_id = dev;
            return config_226(ctx);
        }
    }

    return -1;
}

int ina_read(const ina_ctx_t *ctx, ina_sample_t *s)
{
    s->temp_mc = INT32_MIN;

    if (ctx->chip == INA_CHIP_228) {
        int32_t vbus20 = 0, vsh20 = 0, cur20 = 0;
        uint16_t temp = 0;

        if (read_s20(ctx->addr, R228_VBUS, &vbus20) != 0) {
            return -1;
        }
        if (read_s20(ctx->addr, R228_VSHUNT, &vsh20) != 0) {
            return -1;
        }
        if (read_s20(ctx->addr, R228_CURRENT, &cur20) != 0) {
            return -1;
        }
        if (read_u16(ctx->addr, R228_DIETEMP, &temp) != 0) {
            return -1;
        }

        s->vbus_uv        = vbus_uv_228(vbus20);
        s->vshunt_nv      = vshunt_nv_228(vsh20);
        s->current_ua     = current_ua_from_shunt(s->vshunt_nv);
        /* CURRENT LSB = Imax / 2^19 = 327.68 A / 524288 = 625 uA */
        s->current_reg_ua = (int32_t)(((int64_t)cur20 * 625));
        s->temp_mc        = temp_mc_228((int16_t)temp);

    } else if (ctx->chip == INA_CHIP_226) {
        uint16_t vbus16 = 0, vsh16 = 0, cur16 = 0;

        if (read_u16(ctx->addr, R226_BUSV, &vbus16) != 0) {
            return -1;
        }
        if (read_u16(ctx->addr, R226_SHUNTV, &vsh16) != 0) {
            return -1;
        }
        if (read_u16(ctx->addr, R226_CURRENT, &cur16) != 0) {
            return -1;
        }

        s->vbus_uv        = VBUS_UV_226(vbus16);
        s->vshunt_nv      = VSHUNT_NV_226((int16_t)vsh16);
        s->current_ua     = current_ua_from_shunt(s->vshunt_nv);
        /* CURRENT LSB = 163.84 A / 32768 = 5 mA */
        s->current_reg_ua = (int32_t)((int16_t)cur16) * 5000;
        /* INA226 has no die-temperature sensor */
        s->temp_mc        = INT32_MIN;

    } else {
        return -1;
    }

    s->power_mw = (int32_t)(((int64_t)s->vbus_uv * s->current_ua) / 1000000000);

    return 0;
}
