/**
 * pmu.h — PM02D power-module (battery telemetry) layer
 *
 * Wraps the INA226/INA228 driver: init with AF auto-detection, one reading per
 * call, battery counters (mAh / Wh) and a snapshot for telemetry.
 */
#ifndef PMU_H
#define PMU_H

#include <stdint.h>

typedef struct {
    uint8_t  chip;        /* 0 = none, see ina_chip_t */
    uint8_t  addr;        /* 7-bit I2C address in use  */
    uint8_t  af;          /* I2C1 pin alternate function that worked */
    uint32_t samples;
    uint32_t errors;
    int32_t  vbus_mv;     /* battery voltage   [mV] */
    int32_t  current_ma;  /* current, + = discharge [mA] */
    int32_t  power_mw;    /* V * I             [mW] */
    int32_t  temp_mc;     /* INA228 die temp [milli-degC]; INT32_MIN = n/a */
    int64_t  charge_uah;  /* coulomb counter   [uAh] */
    int64_t  energy_uwh;  /* energy counter    [uWh] */
} pmu_data_t;

/* Probe + configure the monitor. 0 = ready, -1 = not found. */
int pmu_init(void);

/* Take one reading and advance the counters by dt_ms. 0 = ok. */
int pmu_read(uint32_t dt_ms);

const pmu_data_t *pmu_data(void);

void pmu_zero_counters(void);

/* 1 while the module is being polled, 0 after it stops answering. */
int pmu_is_online(void);

#endif /* PMU_H */
