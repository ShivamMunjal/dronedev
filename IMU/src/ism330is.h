/*
 * ism330is.h - ISM330IS 6-axis IMU driver (I2C), integer only.
 *
 * Register addresses, the WHO_AM_I value, the full-scale encodings and the
 * CTRL3_C bit positions were all taken from ST's own driver header
 * (ism330is_reg.h, shipped inside MEMS Studio) rather than from memory:
 *
 *   WHO_AM_I    0x0F -> 0x22
 *   CTRL1_XL    0x10   accel: [7:4] ODR, [3:2] FS
 *   CTRL2_G     0x11   gyro : [7:4] ODR, [3:2] FS, [0] FS_125
 *   CTRL3_C     0x12   bit2 IF_INC (auto-increment), bit6 BDU (block update)
 *   OUTX_L_G    0x22   gyro  X/Y/Z int16 LE = 0x22..0x27
 *   OUTX_L_A    0x28   accel X/Y/Z int16 LE = 0x28..0x2D
 *
 * Gyro and accel outputs are contiguous, so one 12-byte burst read starting at
 * OUTX_L_G fetches a complete inertial sample in a single I2C transaction.
 */
#ifndef ISM330IS_H
#define ISM330IS_H

#include <stdint.h>

/* Register map */
#define ISM_WHO_AM_I        0x0Fu
#define ISM_CTRL1_XL        0x10u
#define ISM_CTRL2_G         0x11u
#define ISM_CTRL3_C         0x12u
#define ISM_CTRL6_C         0x15u
#define ISM_CTRL7_G         0x16u
#define ISM_OUT_TEMP_L      0x20u
#define ISM_OUTX_L_G        0x22u

/* CTRL3_C bits - bit positions verified against ism330is_reg.h bitfields */
#define ISM_CTRL3_SW_RESET  0x01u
#define ISM_CTRL3_IF_INC    0x04u
#define ISM_CTRL3_BDU       0x40u

/* WHO_AM_I value */
#define ISM_ID_ISM330IS     0x22u

/* ODR codes for CTRL1_XL / CTRL2_G bits [7:4] (high-performance mode) */
#define ISM_ODR_OFF         0u
#define ISM_ODR_12H5        1u
#define ISM_ODR_26          2u
#define ISM_ODR_52          3u
#define ISM_ODR_104         4u
#define ISM_ODR_208         5u
#define ISM_ODR_416         6u
#define ISM_ODR_833         7u
#define ISM_ODR_1667        8u
#define ISM_ODR_3333        9u
#define ISM_ODR_6667        10u

/* Accel full-scale codes for CTRL1_XL bits [3:2] */
#define ISM_XL_FS_2G        0u
#define ISM_XL_FS_16G       1u
#define ISM_XL_FS_4G        2u
#define ISM_XL_FS_8G        3u

/* Gyro full-scale codes for CTRL2_G bits [3:2] (125 dps uses a separate bit) */
#define ISM_G_FS_250        0u
#define ISM_G_FS_500        1u
#define ISM_G_FS_1000       2u
#define ISM_G_FS_2000       3u

/* One inertial sample. Raw counts are kept because the control path wants
 * counts (no scaling needed), while the scaled values are handy for the GUI. */
typedef struct {
    int16_t gx, gy, gz;      /* gyro, raw int16 LSB   */
    int16_t ax, ay, az;      /* accel, raw int16 LSB  */
    int16_t temp_raw;        /* die temperature, raw  */
} ism_sample_t;

/* Probe for the device and configure it. Tries both possible I2C addresses.
 * Returns 0 on success, -1 if no ISM330IS answered, -2 if the WHO_AM_I value
 * came back as something else (reported through *who_out). */
int ism_init(uint8_t *addr_used, uint8_t *who_out);

/* Raw single-byte register access (exposed for a bus scan / debugging). */
int ism_read_reg(uint8_t reg, uint8_t *val);
int ism_write_reg(uint8_t reg, uint8_t val);

/* Read one complete inertial sample with a single 12-byte burst read.
 * Returns 0 on success, negative on I2C error. */
int ism_read_sample(ism_sample_t *s);

/* Configure ranges/rates at runtime (codes above). Returns 0 on success. */
int ism_set_odr(uint8_t xl_odr, uint8_t g_odr);
int ism_set_fs(uint8_t xl_fs, uint8_t g_fs);

/* Current sensitivity, in micro-units per LSB, derived from the active FS.
 * e.g. *accel_ug = 122 (ug/LSB) for +-4 g, *gyro_mdps = 15259 (mdps/LSB). */
void ism_sensitivity(uint32_t *accel_ug, uint32_t *gyro_mdps);

/* Address the driver is currently using (0 if ism_init() has not succeeded). */
uint8_t ism_addr(void);

/* Die temperature in milli-degrees C. */
int32_t ism_temp_mdegC(int16_t raw);

#endif /* ISM330IS_H */
