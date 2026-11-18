/* sensors.c — ISM330IS, INA228/INA226, Mahony AHRS (float, M55 FPU) */
#include "sensors.h"
#include "board_n6.h"
#include <math.h>

/* ───────────────────────── ISM330IS ───────────────────────── */
#define ISM_ADDR      0x6Au
#define ISM_WHO_AM_I  0x0Fu
#define ISM_CTRL1_XL  0x10u
#define ISM_CTRL2_G   0x11u
#define ISM_CTRL3_C   0x12u
#define ISM_OUTX_L_G  0x22u

static int ism_ok;
static float g_bias[3];

int imu_init(void)
{
    uint8_t id = 0;
    if (n6_i2c_mem_read(ISM_ADDR, ISM_WHO_AM_I, &id, 1) != 0) return -1;
    if (id != 0x22u) return -2;

    uint8_t v;
    v = 0x01; n6_i2c_mem_write(ISM_ADDR, ISM_CTRL3_C, &v, 1);   /* SW_RESET */
    HAL_Delay(20);
    v = 0x44; n6_i2c_mem_write(ISM_ADDR, ISM_CTRL3_C, &v, 1);   /* BDU | IF_INC */
    v = 0x68; n6_i2c_mem_write(ISM_ADDR, ISM_CTRL1_XL, &v, 1);  /* 416 Hz, +/-4 g */
    v = 0x6C; n6_i2c_mem_write(ISM_ADDR, ISM_CTRL2_G,  &v, 1);  /* 416 Hz, 2000 dps */
    HAL_Delay(30);
    ism_ok = 1;
    return 0;
}

int imu_read(int16_t g[3], int16_t a[3])
{
    uint8_t b[12];
    if (!ism_ok) return -1;
    if (n6_i2c_mem_read(ISM_ADDR, ISM_OUTX_L_G, b, 12) != 0) return -1;
    for (int i = 0; i < 3; i++) {
        g[i] = (int16_t)((uint16_t)b[2 * i] | ((uint16_t)b[2 * i + 1] << 8));
        a[i] = (int16_t)((uint16_t)b[6 + 2 * i] | ((uint16_t)b[7 + 2 * i] << 8));
    }
    return 0;
}

/* ───────────────────────── INA228 / INA226 ───────────────────────── */
#define INA228_ADDR 0x45u
#define INA226_ADDR 0x41u
#define R228_CONFIG 0x00u
#define R228_ADC    0x01u
#define R228_VSHUNT 0x04u
#define R228_VBUS   0x05u
#define R228_DIETEMP 0x06u
#define R226_CONFIG 0x00u
#define R226_SHUNTV 0x01u
#define R226_BUSV   0x02u

static uint8_t ina_addr;      /* 0 = none */
static int     ina_is228;

int pmu_init_n6(void)
{
    uint8_t b[2];
    if (n6_i2c_mem_read(INA228_ADDR, R228_CONFIG, b, 2) == 0) {
        ina_addr = INA228_ADDR; ina_is228 = 1;
        uint8_t cfg[2] = { 0x00, 0x00 };                 /* ADC range ±163.84 mV */
        n6_i2c_mem_write(ina_addr, R228_CONFIG, cfg, 2);
        uint8_t adc[2] = { (uint8_t)(0xF922u >> 8), (uint8_t)(0xF922u & 0xFF) };
        n6_i2c_mem_write(ina_addr, R228_ADC, adc, 2);
        HAL_Delay(10);
        return 0;
    }
    if (n6_i2c_mem_read(INA226_ADDR, R226_CONFIG, b, 2) == 0) {
        ina_addr = INA226_ADDR; ina_is228 = 0;
        uint8_t cfg[2] = { 0x45, 0x27 };                 /* 16 avg, 1.1ms, cont. */
        n6_i2c_mem_write(ina_addr, R226_CONFIG, cfg, 2);
        HAL_Delay(10);
        return 0;
    }
    ina_addr = 0;
    return -1;
}

const char *pmu_probe_name(void)
{ return ina_addr == 0 ? "NONE" : (ina_is228 ? "INA228,69" : "INA226,65"); }

int pmu_read_n6(int32_t *mv, int32_t *ma)
{
    uint8_t b[3];
    if (!ina_addr) return -1;
    if (ina_is228) {
        if (n6_i2c_mem_read(ina_addr, R228_VBUS, b, 3) != 0) return -1;
        int32_t raw = (int32_t)(((uint32_t)b[0] << 16 | (uint32_t)b[1] << 8 | b[2]) >> 4 & 0xFFFFF);
        *mv = (int32_t)(((int64_t)raw * 3125) / 16000);          /* 195.3125 uV/LSB */
        if (n6_i2c_mem_read(ina_addr, R228_VSHUNT, b, 3) != 0) return -1;
        int32_t sh = (int32_t)(((uint32_t)b[0] << 16 | (uint32_t)b[1] << 8 | b[2]) >> 4 & 0xFFFFF);
        if (sh & 0x80000) sh -= 0x100000;                        /* sign extend 20-bit */
        /* Vshunt LSB = 312.5 nV ; R = 500 uOhm -> mA = uV * 2 */
        int32_t uvn = (int32_t)(((int64_t)sh * 625) / 2);        /* nano-volt-ish */
        *ma = (int32_t)(uvn / 500);                              /* nV/500uOhm -> nA/1000 = ... */
        *ma = (int32_t)(((int64_t)sh * 625 / 2) / 500);
    } else {
        if (n6_i2c_mem_read(ina_addr, R226_BUSV, b, 2) != 0) return -1;
        *mv = (int32_t)(((uint16_t)b[0] << 8 | b[1]) * 125 / 100);   /* 1.25 mV/LSB */
        if (n6_i2c_mem_read(ina_addr, R226_SHUNTV, b, 2) != 0) return -1;
        int16_t sh = (int16_t)((uint16_t)b[0] << 8 | b[1]);
        *ma = (int32_t)(((int32_t)sh * 25) / 10 / 5);               /* 2.5uV/LSB / 0.5mOhm */
    }
    return 0;
}

/* ───────────────────────── Mahony AHRS ───────────────────────── */
static float q0 = 1.0f, q1, q2, q3;
static float twoKp = 1.2f, twoKi = 0.02f;
static float ix, iy, iz;
static float z_roll, z_pitch, z_yaw;

#define GYRO_MDPS_PER_LSB  (70.0f)        /* 2000 dps / 32768 */
#define ACC_MG_PER_LSB     (0.122f)       /* 4 g / 32768 * 1000 */

static float rad2deg(float r) { return r * 57.2957795f; }

void ahrs_init(void) { q0 = 1; q1 = q2 = q3 = 0; ix = iy = iz = 0; }

void ahrs_zero(void)
{
    /* capture the current attitude as the new zero reference */
    float r = atan2f(2.0f * (q0 * q1 + q2 * q3), 1 - 2 * (q1 * q1 + q2 * q2));
    float p = asinf(2.0f * (q0 * q2 - q3 * q1));
    float y = atan2f(2.0f * (q0 * q3 + q1 * q2), 1 - 2 * (q2 * q2 + q3 * q3));
    z_roll = r; z_pitch = p; z_yaw = y;
}

void ahrs_update(const int16_t g[3], const int16_t a[3], float dt, float *roll, float *pitch, float *yaw)
{
    if (dt <= 0.0f || dt > 0.2f) dt = 0.01f;

    float gx = ((float)g[0]) * GYRO_MDPS_PER_LSB * 0.0174532925f;  /* rad/s */
    float gy = ((float)g[1]) * GYRO_MDPS_PER_LSB * 0.0174532925f;
    float gz = ((float)g[2]) * GYRO_MDPS_PER_LSB * 0.0174532925f;
    gx -= g_bias[0] * 0.0174532925f;
    gy -= g_bias[1] * 0.0174532925f;
    gz -= g_bias[2] * 0.0174532925f;

    float ax = (float)a[0] * ACC_MG_PER_LSB / 1000.0f;   /* g */
    float ay = (float)a[1] * ACC_MG_PER_LSB / 1000.0f;
    float az = (float)a[2] * ACC_MG_PER_LSB / 1000.0f;
    float an = sqrtf(ax * ax + ay * ay + az * az);
    if (an > 0.0001f) { ax /= an; ay /= an; az /= an; }

    /* estimated direction of gravity */
    float vx = 2.0f * (q1 * q3 - q0 * q2);
    float vy = 2.0f * (q0 * q1 + q2 * q3);
    float vz = q0 * q0 - q1 * q1 - q2 * q2 + q3 * q3;

    float ex = (ay * vz - az * vy);
    float ey = (az * vx - ax * vz);
    float ez = (ax * vy - ay * vx);

    if (an > 0.0001f) {
        ix += twoKi * ex * dt; iy += twoKi * ey * dt; iz += twoKi * ez * dt;
        gx += twoKp * ex + ix;
        gy += twoKp * ey + iy;
        gz += twoKp * ez + iz;
    }

    float h = 0.5f * dt;
    float qa = q0, qb = q1, qc = q2, qd = q3;
    q0 += (-qb * gx - qc * gy - qd * gz) * h;
    q1 += ( qa * gx + qc * gz - qd * gy) * h;
    q2 += ( qa * gy - qb * gz + qd * gx) * h;
    q3 += ( qa * gz + qb * gy - qc * gx) * h;
    float n = sqrtf(q0 * q0 + q1 * q1 + q2 * q2 + q3 * q3);
    if (n > 0.0f) { q0 /= n; q1 /= n; q2 /= n; q3 /= n; }

    float r = atan2f(2.0f * (q0 * q1 + q2 * q3), 1 - 2 * (q1 * q1 + q2 * q2)) - z_roll;
    float p = asinf(2.0f * (q0 * q2 - q3 * q1)) - z_pitch;
    float y = atan2f(2.0f * (q0 * q3 + q1 * q2), 1 - 2 * (q2 * q2 + q3 * q3)) - z_yaw;

    *roll = rad2deg(r);
    *pitch = rad2deg(p);
    *yaw = rad2deg(y);
}
