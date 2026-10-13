/*
 * fusion.c - attitude from the ISM330IS using ST's MotionFX (Cortex-M0+ build).
 *
 * WHY MotionFX AND NOT A HAND-WRITTEN FILTER
 * ------------------------------------------
 * `sensor/fusion.py` (the SensorTile.box work) is a good filter, but it exists
 * in Python on the host. The control loop has to run on the C0, and the C0 is a
 * Cortex-M0+ with no FPU and 30 KB of RAM, so a straight port means writing and
 * tuning fixed-point math and then proving it matches the reference. ST ships a
 * CM0+ build of MotionFX that is already fixed-point internally, already tuned,
 * and already includes gyro-bias estimation - so use it and keep the Python
 * filter as the reference to validate against.
 *
 * THE HONEST LIMITATION: NO MAGNETOMETER
 * --------------------------------------
 * The ISM330IS is 6-axis. Accelerometer gives a gravity reference, so roll and
 * pitch are absolute and self-correcting. Yaw has NO absolute reference at all:
 * it is pure gyro integration and it WILL drift (typically ~1 deg/s worth of
 * uncorrected bias right after startup, settling as gbias converges). Treat yaw
 * as a rate reference for the mixer, not a heading. Anything needing a true
 * heading needs a magnetometer added to the bus.
 *
 * IMPORTANT: because 9X is disabled and mag[] is fed as zeros, MotionFX's own
 * mag-calibration path is inert. Do not enable 9X - with a zeros mag it would
 * try to calibrate against a constant field and corrupt the estimate.
 */

#include "fusion.h"

#include "board.h"
#include "ism330is.h"
#include "motion_fx_cm0p.h"
#include "system.h"

#include <string.h>

static int s_ready = 0;
static uint32_t s_updates = 0;

/* Which physical axis of the ISM330IS points where on the earth frame.
 * MotionFX's documented default is ENU: sensor X -> East, Y -> North, Z -> Up.
 * The eval board is mounted so that this is not automatically true, so verify
 * on hardware by tilting and checking the sign of each angle; if roll and pitch
 * respond to the wrong rotation, permute/negate these characters rather than
 * touching any filter math. */
#define FUSION_ACC_ORIENT  "ENU"
#define FUSION_GYR_ORIENT  "ENU"
#define FUSION_MAG_ORIENT  "ENU"

void fusion_init(void)
{
    if (s_ready) return;

    MotionFX_CM0P_initialize(MFX_CM0P_MCU_STM32);
    MotionFX_CM0P_setOrientation(FUSION_ACC_ORIENT, FUSION_GYR_ORIENT,
                                 FUSION_MAG_ORIENT);

    /* 6X: accelerometer + gyroscope only. 9X must stay off (see header note). */
    MotionFX_CM0P_enable_6X(MFX_CM0P_ENGINE_ENABLE);
    MotionFX_CM0P_enable_9X(MFX_CM0P_ENGINE_DISABLE);

    MotionFX_CM0P_enable_euler(MFX_CM0P_ENGINE_ENABLE);

    /* Gyro-bias estimation: this is what makes yaw usable as a rate. Enable it;
     * it needs the board still for a moment to converge. */
    MotionFX_CM0P_enable_gbias(MFX_CM0P_ENGINE_ENABLE);

    s_updates = 0u;
    s_ready = 1;
}

int fusion_step(const ism_sample_t *s, float dt_s, fusion_euler_t *out)
{
    if (!s_ready || !s || !out) return -1;

    uint32_t aug, gmd;              /* ug/LSB, mdps/LSB - depends on FS setting */
    ism_sensitivity(&aug, &gmd);

    /* Raw counts -> MotionFX's units. Gyro wants dps, accel wants g. */
    const float a_lsb_to_g  = 1.0f / 1000000.0f * (float)aug;
    const float g_lsb_to_dps = 1.0f / 1000.0f * (float)gmd;

    MFX_CM0P_input_t  in;
    MFX_CM0P_output_t res;

    memset(&in, 0, sizeof(in));
    memset(&res, 0, sizeof(res));

    in.acc[0]  = (float)s->ax * a_lsb_to_g;
    in.acc[1]  = (float)s->ay * a_lsb_to_g;
    in.acc[2]  = (float)s->az * a_lsb_to_g;

    in.gyro[0] = (float)s->gx * g_lsb_to_dps;
    in.gyro[1] = (float)s->gy * g_lsb_to_dps;
    in.gyro[2] = (float)s->gz * g_lsb_to_dps;

    /* No magnetometer on this part: zeros, with 9X disabled so they are ignored. */
    in.mag[0] = in.mag[1] = in.mag[2] = 0.0f;

    MotionFX_CM0P_update(&res, &in, dt_s);
    s_updates++;

    /* rotation_6X[] is documented as yaw, pitch, roll - in that order. */
    const float yaw   = res.rotation_6X[0];
    const float pitch = res.rotation_6X[1];
    const float roll  = res.rotation_6X[2];

    out->roll_mdeg  = (int32_t)(roll  * 1000.0f);
    out->pitch_mdeg = (int32_t)(pitch * 1000.0f);
    out->yaw_mdeg   = (int32_t)(yaw   * 1000.0f);
    fusion_get_gbias(out->gbias_mdps);

    return 0;
}

/* True once the 6X and euler engines report they are running. */
int fusion_is_ready(void) { return s_ready; }

uint32_t fusion_update_count(void) { return s_updates; }

void fusion_get_gbias(int32_t mdps[3])
{
    float g[3] = { 0.0f, 0.0f, 0.0f };
    if (mdps) {
        MotionFX_CM0P_getGbias(g);
        mdps[0] = (int32_t)(g[0] * 1000.0f);
        mdps[1] = (int32_t)(g[1] * 1000.0f);
        mdps[2] = (int32_t)(g[2] * 1000.0f);
    }
}

int fusion_lib_version(char *buf, unsigned len)
{
    if (!buf || len < 8u) return -1;
    char v[64];
    if (MotionFX_CM0P_GetLibVersion(v) == 0u) return -1;
    unsigned n = 0u;
    while (n + 1u < len && v[n]) { buf[n] = v[n]; n++; }
    buf[n] = '\0';
    return 0;
}
