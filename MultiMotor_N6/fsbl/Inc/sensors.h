#ifndef SENSORS_H
#define SENSORS_H
#include <stdint.h>
/* ISM330IS: 6-axis, I2C @0x6A (SA0=GND, CS=3V3). Returns 0 on success. */
int  imu_init(void);
int  imu_read(int16_t g[3], int16_t a[3]);
/* INA228 (PM02D HV) @0x45, fallback INA226 @0x41. */
int  pmu_init_n6(void);
int  pmu_read_n6(int32_t *mv, int32_t *ma);
const char *pmu_probe_name(void);
/* Mahony 6-DOF AHRS -> degrees */
void ahrs_init(void);
void ahrs_update(const int16_t g[3], const int16_t a[3], float dt,
                 float *roll, float *pitch, float *yaw);
void ahrs_zero(void);
#endif
