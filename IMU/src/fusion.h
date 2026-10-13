/*
 * fusion.h - attitude from the ISM330IS via ST MotionFX (Cortex-M0+ build).
 *
 * Output is milli-degrees so the control path never has to touch floats.
 * See fusion.c for why MotionFX is used and for the yaw-drift caveat.
 */

#ifndef FUSION_H
#define FUSION_H

#include <stdint.h>

#include "ism330is.h"

typedef struct {
    int32_t roll_mdeg;      /* + = right wing down  (MotionFX convention) */
    int32_t pitch_mdeg;     /* + = nose up */
    int32_t yaw_mdeg;       /* gyro-integrated - DRIFTS, see fusion.c      */
    int32_t gbias_mdps[3];  /* estimated gyro bias, mdps                   */
} fusion_euler_t;

/* Configure MotionFX. Safe to call repeatedly. */
void fusion_init(void);

/* One filter step. dt_s is seconds since the previous step.
 * Returns 0 on success. */
int fusion_step(const ism_sample_t *s, float dt_s, fusion_euler_t *out);

int fusion_is_ready(void);
uint32_t fusion_update_count(void);

/* Writes the library version string, e.g. "1.2.3". Returns 0 on success. */
int fusion_lib_version(char *buf, unsigned len);

void fusion_get_gbias(int32_t mdps[3]);

#endif /* FUSION_H */
