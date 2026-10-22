/**
 * mixer.c — configurable-geometry motor mixer (see mixer.h for conventions)
 *
 * Pure integer maths: the STM32C0 is a Cortex-M0+ with no FPU, and this runs
 * in the control path, so there is no floating point anywhere.
 *
 * Mixing model, for motor i at angle A_i:
 *     delta_i = ( roll * (-sin A_i) + pitch * (-cos A_i) + yaw * yaw_dir_i ) >> 15
 *     out_i   = throttle + delta_i
 *
 * The signs are chosen so that, per the convention in mixer.h:
 *   roll  > 0 (roll right)  -> motors on the right (sin > 0) slow down
 *   pitch > 0 (nose up)     -> motors at the front (cos > 0) slow down
 *   yaw   > 0 (yaw right)   -> yaw_dir = +1 motors speed up
 *
 * The limiter is the part that matters for a flyable mixer: if the requested
 * outputs do not fit in [1000, 2000] us it first SCALES the attitude deltas
 * down (only if the control spread alone is wider than the whole range), then
 * SHIFTS all outputs together so the attitude differences are preserved and
 * only the collective suffers. Naive per-motor clipping would instead destroy
 * the attitude command and flip the aircraft.
 */
#include "mixer.h"

/* sin(deg) in Q15 for 0..90 deg, exact at integer degrees */
static const int16_t sin_q15_tab[91] = {
         0,    572,   1144,   1715,   2286,   2856,   3425,   3993,   4560,
      5126,   5690,   6252,   6813,   7371,   7927,   8481,   9032,   9580,
     10126,  10668,  11207,  11743,  12275,  12803,  13328,  13848,  14364,
     14876,  15383,  15886,  16383,  16876,  17364,  17846,  18323,  18794,
     19260,  19720,  20173,  20621,  21062,  21497,  21925,  22347,  22762,
     23170,  23571,  23964,  24351,  24730,  25101,  25465,  25821,  26169,
     26509,  26841,  27165,  27481,  27788,  28087,  28377,  28659,  28932,
     29196,  29451,  29697,  29934,  30162,  30381,  30591,  30791,  30982,
     31163,  31335,  31498,  31650,  31794,  31927,  32051,  32165,  32269,
     32364,  32448,  32523,  32587,  32642,  32687,  32722,  32747,  32762,
     32767,
};

mixer_motor_t mixer_motors[MIXER_MOTORS];

/* sin over the full circle, integer degrees, result in Q15 (-32767..32767) */
static int32_t sin_q15(int32_t deg)
{
    deg %= 360;
    if (deg < 0) {
        deg += 360;
    }

    if (deg <= 90) {
        return sin_q15_tab[deg];
    }
    if (deg <= 180) {
        return sin_q15_tab[180 - deg];
    }
    if (deg <= 270) {
        return -sin_q15_tab[deg - 180];
    }
    return -sin_q15_tab[360 - deg];
}

static int32_t cos_q15(int32_t deg)
{
    return sin_q15(deg + 90);
}

static void recompute_gains(mixer_motor_t *m)
{
    m->roll_gain  = -sin_q15(m->angle_deg);          /* right side slows when rolling right */
    m->pitch_gain = -cos_q15(m->angle_deg);          /* nose slows when pitching nose up    */
    m->yaw_gain   = (int32_t)m->yaw_dir * 32767;
}

void mixer_init(void)
{
    mixer_load_preset(MIXER_PRESET_HEXA_X);
}

int mixer_preset_from_char(char c)
{
    if (c == '1') return MIXER_PRESET_HEXA_X;
    if (c == '2') return MIXER_PRESET_HEXA_P;
    if (c == '3') return MIXER_PRESET_QUAD_X;
    return -1;
}

void mixer_load_preset(mixer_preset_t preset)
{
    /* CCW/CW alternates around the frame in every one of these layouts */
    switch (preset) {
    case MIXER_PRESET_HEXA_P:
        for (int i = 0; i < MIXER_MOTORS; i++) {
            mixer_motors[i].angle_deg = (int16_t)(i * 60);
            mixer_motors[i].yaw_dir   = (i & 1) ? -1 : 1;
            mixer_motors[i].enabled   = 1;
        }
        break;

    case MIXER_PRESET_QUAD_X:
        for (int i = 0; i < MIXER_MOTORS; i++) {
            mixer_motors[i].angle_deg = (int16_t)(45 + i * 90);
            mixer_motors[i].yaw_dir   = (i & 1) ? -1 : 1;
            mixer_motors[i].enabled   = (i < 4) ? 1 : 0;   /* 4 motors on 1..4 */
        }
        break;

    case MIXER_PRESET_HEXA_X:
    default: {
        /* Default layout (motor order M1..M6). Angles are the hexa-X set but
         * the frames are wired in a different rotational order, so this is an
         * explicit table rather than a 30 + i*60 formula. */
        static const int16_t hexa_x_angle[MIXER_MOTORS] = { 30, 90, 210, 270, 150, 330 };
        static const int8_t  hexa_x_dir  [MIXER_MOTORS] = { -1,  1,   1,  -1,  -1,   1 };
        for (int i = 0; i < MIXER_MOTORS; i++) {
            mixer_motors[i].angle_deg = hexa_x_angle[i];
            mixer_motors[i].yaw_dir   = hexa_x_dir[i];
            mixer_motors[i].enabled   = 1;
        }
        break;
    }
    }

    for (int i = 0; i < MIXER_MOTORS; i++) {
        recompute_gains(&mixer_motors[i]);
    }
}

int mixer_set_motor(int index, int angle_deg, int yaw_dir)
{
    if (index < 0 || index >= MIXER_MOTORS) {
        return -1;
    }
    if (yaw_dir != 1 && yaw_dir != -1) {
        return -1;
    }

    angle_deg %= 360;
    if (angle_deg < 0) {
        angle_deg += 360;
    }

    mixer_motors[index].angle_deg = (int16_t)angle_deg;
    mixer_motors[index].yaw_dir   = (int8_t)yaw_dir;
    recompute_gains(&mixer_motors[index]);
    return 0;
}

int mixer_set_enabled(int index, int enabled)
{
    if (index < 0 || index >= MIXER_MOTORS) {
        return -1;
    }
    mixer_motors[index].enabled = enabled ? 1 : 0;
    return 0;
}

void mixer_apply(int32_t thr, int32_t roll, int32_t pitch, int32_t yaw,
                 mixer_result_t *res)
{
    int32_t delta[MIXER_MOTORS];
    int32_t dmin = 0, dmax = 0;
    int active = 0;

    /* --- 1. attitude deltas ------------------------------------------- */
    for (int i = 0; i < MIXER_MOTORS; i++) {
        const mixer_motor_t *m = &mixer_motors[i];

        if (!m->enabled) {
            delta[i] = 0;
            continue;
        }
        active++;

        delta[i] = (roll  * m->roll_gain +
                    pitch * m->pitch_gain +
                    yaw   * m->yaw_gain) >> 15;

        if (active == 1) {
            dmin = dmax = delta[i];
        } else {
            if (delta[i] < dmin) dmin = delta[i];
            if (delta[i] > dmax) dmax = delta[i];
        }
    }

    if (active == 0) {
        /* Nothing in the mix: command every output to idle. */
        for (int i = 0; i < MIXER_MOTORS; i++) {
            res->out[i] = MIXER_IDLE_US;
        }
        res->limit = MIX_OK;
        res->thr_used = MIXER_IDLE_US;
        return;
    }

    res->limit = MIX_OK;

    /* --- 2. if the attitude spread alone cannot fit, scale it ---------- */
    const int32_t span  = dmax - dmin;
    const int32_t avail = MIXER_MAX_US - MIXER_MIN_US;

    if (span > avail) {
        const int32_t scale = (avail << 15) / span;    /* Q15 */
        dmin = 0; dmax = 0;
        active = 0;
        for (int i = 0; i < MIXER_MOTORS; i++) {
            if (!mixer_motors[i].enabled) {
                continue;
            }
            delta[i] = (delta[i] * scale) >> 15;
            if (active++ == 0) {
                dmin = dmax = delta[i];
            } else {
                if (delta[i] < dmin) dmin = delta[i];
                if (delta[i] > dmax) dmax = delta[i];
            }
        }
        res->limit = MIX_SCALED;
    }

    /* --- 3. shift the whole set so it fits (attitude preserved) -------- */
    int32_t shift = 0;
    if (thr + dmax > MIXER_MAX_US) {
        shift = MIXER_MAX_US - (thr + dmax);
    }
    if (thr + dmin + shift < MIXER_MIN_US) {
        shift += MIXER_MIN_US - (thr + dmin + shift);
    }
    if (shift != 0 && res->limit == MIX_OK) {
        res->limit = MIX_SHIFTED;
    }

    res->thr_used = thr + shift;

    /* --- 4. final per-motor clamp (safety net) ------------------------- */
    for (int i = 0; i < MIXER_MOTORS; i++) {
        if (!mixer_motors[i].enabled) {
            /* A motor outside the mix is held at idle, never at throttle:
             * an unused output with an ESC on it must not spin up. */
            res->out[i] = MIXER_IDLE_US;
            continue;
        }
        int32_t v = thr + delta[i] + shift;
        if (v < MIXER_MIN_US) v = MIXER_MIN_US;
        if (v > MIXER_MAX_US) v = MIXER_MAX_US;
        res->out[i] = (uint16_t)v;
    }
}

/* ── Geometry persistence ─────────────────────────────────────────────────
 * Only the *inputs* (angle, direction, enabled) are stored — roll/pitch/yaw
 * gains are derived, so they are recomputed on load by mixer_set_motor()
 * instead of being persisted. That keeps a stored record small and means a
 * future change to the gain maths cannot leave stale derived values in flash.
 */
#include "flashcfg.h"

#define MIXER_CFG_MAGIC   0x4D584731u   /* "MXG1" */
#define MIXER_CFG_VERSION 1u

typedef struct {
    int16_t angle_deg;
    int16_t yaw_dir;
    int16_t enabled;
    int16_t reserved;
} mixer_cfg_motor_t;

typedef struct {
    uint32_t magic;
    uint32_t version;
    mixer_cfg_motor_t m[MIXER_MOTORS];
} mixer_cfg_t;                          /* 8 + 6*8 = 56 bytes, 8-byte aligned */

int mixer_save(void)
{
    mixer_cfg_t cfg;
    cfg.magic   = MIXER_CFG_MAGIC;
    cfg.version = MIXER_CFG_VERSION;

    for (int i = 0; i < MIXER_MOTORS; i++) {
        cfg.m[i].angle_deg = mixer_motors[i].angle_deg;
        cfg.m[i].yaw_dir   = mixer_motors[i].yaw_dir;
        cfg.m[i].enabled   = (int16_t)mixer_motors[i].enabled;
        cfg.m[i].reserved  = 0;
    }

    return flashcfg_write(&cfg, sizeof(cfg));
}

int mixer_load(void)
{
    mixer_cfg_t cfg;

    if (flashcfg_read(&cfg, sizeof(cfg)) != (int)sizeof(cfg)) return -1;
    if (cfg.magic != MIXER_CFG_MAGIC || cfg.version != MIXER_CFG_VERSION) return -1;

    for (int i = 0; i < MIXER_MOTORS; i++) {
        /* set_motor validates the direction, so corrupt data is rejected
         * rather than silently producing a wrong mixer. */
        if (mixer_set_motor(i, cfg.m[i].angle_deg, cfg.m[i].yaw_dir) != 0) return -1;
        mixer_set_enabled(i, cfg.m[i].enabled);
    }
    return 0;
}
