#ifndef INA2XX_H
#define INA2XX_H

#include <stdint.h>

typedef enum {
    INA_CHIP_NONE = 0,
    INA_CHIP_226,   /* Holybro PM02D low-voltage (6S)  variant */
    INA_CHIP_228    /* Holybro PM02D high-voltage (2S-12S, this one) */
} ina_chip_t;

typedef struct {
    ina_chip_t chip;
    uint8_t    addr;        /* 7-bit I2C address            */
    uint16_t   mfg_id;      /* 0x5449 = Texas Instruments   */
    uint16_t   dev_id;
    uint16_t   config;      /* value written to CONFIG      */
    uint16_t   cal;         /* value written to SHUNT_CAL   */
} ina_ctx_t;

typedef struct {
    int32_t vbus_uv;        /* bus voltage        [uV] */
    int32_t vshunt_nv;      /* shunt voltage      [nV] */
    int32_t current_ua;     /* current from Vshunt/R   */
    int32_t current_reg_ua; /* current from the CURRENT register */
    int32_t power_mw;       /* V * I              [mW] */
    int32_t temp_mc;        /* die temp [mC]; INT32_MIN if unsupported */
} ina_sample_t;

const char *ina_chip_name(ina_chip_t chip);

/* Probe the bus, identify the chip and configure it. 0 on success. */
int ina_open(ina_ctx_t *ctx);

/* One measurement. 0 on success. */
int ina_read(const ina_ctx_t *ctx, ina_sample_t *s);

/* Print identification + raw registers (bring-up aid). */
void ina_dump(const ina_ctx_t *ctx);

#endif /* INA2XX_H */
