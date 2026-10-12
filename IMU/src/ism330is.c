/*
 * ism330is.c - ISM330IS 6-axis IMU over I2C. Integer arithmetic only.
 *
 * See ism330is.h for where every register address and bit position came from.
 * The one thing worth repeating: the gyro and accel outputs are contiguous
 * (0x22..0x2D), so a whole inertial sample is ONE 12-byte burst read. With
 * IF_INC set the device auto-increments the address, which is what makes that
 * legal.
 */
#include "ism330is.h"
#include "board.h"
#include "i2c.h"
#include "system.h"

static uint8_t s_addr;         /* 0 until ism_init() succeeds */
static uint8_t s_xl_fs = ISM_XL_FS_4G;
static uint8_t s_g_fs  = ISM_G_FS_500;
static uint8_t s_xl_odr = ISM_ODR_416;
static uint8_t s_g_odr  = ISM_ODR_416;

uint8_t ism_addr(void) { return s_addr; }

int ism_read_reg(uint8_t reg, uint8_t *val)
{
    if (s_addr == 0u) return -1;
    return i2c_read_reg(s_addr, reg, val, 1u);
}

int ism_write_reg(uint8_t reg, uint8_t val)
{
    if (s_addr == 0u) return -1;
    return i2c_write_reg8(s_addr, reg, val);
}

/* Try one address: read WHO_AM_I and check it against the expected value.
 * Returns 0 on a match, -1 if nothing answered, -2 if the wrong value came
 * back (the caller reports it - a wrong ID usually means a different part). */
static int probe_addr(uint8_t addr, uint8_t *who_out)
{
    uint8_t who = 0u;
    s_addr = addr;

    if (i2c_ping(addr) != 0) return -1;
    if (ism_read_reg(ISM_WHO_AM_I, &who) != 0) return -1;

    *who_out = who;
    if (who != ISM_ID_ISM330IS) return -2;
    return 0;
}

int ism_init(uint8_t *addr_used, uint8_t *who_out)
{
    uint8_t who = 0u;
    uint8_t last_who = 0u;
    int rc = -1;

    const uint8_t addrs[2] = { ISM330IS_ADDR_LO, ISM330IS_ADDR_HI };

    s_addr = 0u;
    for (int i = 0; i < 2; i++) {
        rc = probe_addr(addrs[i], &who);
        if (rc <= 0) {
            last_who = who;
            break;
        }
        last_who = who;
        s_addr = 0u;
    }

    if (who_out) *who_out = last_who;
    if (rc == -1) { s_addr = 0u; return -1; }
    if (rc == -2) { s_addr = 0u; return -2; }
    if (addr_used) *addr_used = s_addr;

    /* Software reset, then wait for it to come back. */
    (void)ism_write_reg(ISM_CTRL3_C, ISM_CTRL3_SW_RESET);
    delay_ms(20);

    /* BDU: registers are not updated until both bytes are read, so a sample
     * cannot be torn by concurrent output-register refresh - essential when
     * polling from a control loop.
     * IF_INC: auto-increment, which makes the 12-byte burst read work. */
    if (ism_write_reg(ISM_CTRL3_C, ISM_CTRL3_BDU | ISM_CTRL3_IF_INC) != 0) return -3;

    if (ism_set_odr(ISM330IS_DEF_XL_ODR, ISM330IS_DEF_G_ODR) != 0) return -4;
    if (ism_set_fs(ISM330IS_DEF_XL_FS, ISM330IS_DEF_G_FS) != 0) return -5;

    return 0;
}

int ism_set_odr(uint8_t xl_odr, uint8_t g_odr)
{
    if (xl_odr > ISM_ODR_6667 || g_odr > ISM_ODR_6667) return -1;

    /* CTRL1_XL: [7:4] ODR, [3:2] FS  (FS bits are rewritten unchanged) */
    uint8_t ctrl1 = (uint8_t)((xl_odr << 4) | ((s_xl_fs & 0x03u) << 2));
    uint8_t ctrl2 = (uint8_t)((g_odr  << 4) | ((s_g_fs  & 0x03u) << 2));

    if (ism_write_reg(ISM_CTRL1_XL, ctrl1) != 0) return -1;
    if (ism_write_reg(ISM_CTRL2_G,  ctrl2) != 0) return -1;

    s_xl_odr = xl_odr;
    s_g_odr  = g_odr;
    return 0;
}

int ism_set_fs(uint8_t xl_fs, uint8_t g_fs)
{
    if (xl_fs > ISM_XL_FS_8G || g_fs > ISM_G_FS_2000) return -1;

    s_xl_fs = xl_fs;
    s_g_fs  = g_fs;

    /* Re-apply with the rates the caller actually selected, not the defaults -
     * otherwise changing FS would silently reset a runtime ODR change. */
    return ism_set_odr(s_xl_odr, s_g_odr);
}

int ism_read_sample(ism_sample_t *s)
{
    uint8_t b[12];
    uint8_t t[2];

    if (s_addr == 0u || s == 0) return -1;

    /* One burst: gyro X/Y/Z then accel X/Y/Z, little-endian int16 */
    if (i2c_read_reg(s_addr, ISM_OUTX_L_G, b, sizeof(b)) != 0) return -2;

    s->gx = (int16_t)((uint16_t)b[0] | ((uint16_t)b[1] << 8));
    s->gy = (int16_t)((uint16_t)b[2] | ((uint16_t)b[3] << 8));
    s->gz = (int16_t)((uint16_t)b[4] | ((uint16_t)b[5] << 8));
    s->ax = (int16_t)((uint16_t)b[6] | ((uint16_t)b[7] << 8));
    s->ay = (int16_t)((uint16_t)b[8] | ((uint16_t)b[9] << 8));
    s->az = (int16_t)((uint16_t)b[10] | ((uint16_t)b[11] << 8));

    /* Temperature is a separate 2-byte read. It is diagnostic only, so a
     * failure here must not invalidate the inertial sample. */
    if (i2c_read_reg(s_addr, ISM_OUT_TEMP_L, t, sizeof(t)) == 0) {
        s->temp_raw = (int16_t)((uint16_t)t[0] | ((uint16_t)t[1] << 8));
    } else {
        s->temp_raw = 0;
    }
    return 0;
}

int32_t ism_temp_mdegC(int16_t raw)
{
    /* ST's driver: temp_C = raw/256 + 25. In milli-degrees:
     *   mdegC = raw*1000/256 + 25000 = raw*125/32 + 25000 */
    return ((int32_t)raw * 125) / 32 + 25000;
}

void ism_sensitivity(uint32_t *accel_ug, uint32_t *gyro_mdps)
{
    static const uint16_t xl_g[4] = { 2u, 16u, 4u, 8u };          /* by FS code */
    static const uint16_t g_dps[4] = { 250u, 500u, 1000u, 2000u };

    uint32_t full_g   = xl_g[s_xl_fs & 0x03u];
    uint32_t full_dps = g_dps[s_g_fs & 0x03u];

    if (accel_ug)  *accel_ug  = (full_g * 1000000u) / 32768u;      /* ug per LSB */
    if (gyro_mdps) *gyro_mdps = (full_dps * 1000u) / 32768u;       /* mdps/LSB  */
}
