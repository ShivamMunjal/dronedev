/**
 * mixer.h — configurable-geometry motor mixer
 *
 * Works for any flat multirotor layout: each motor gets a position *angle*
 * around the body Z axis plus a yaw reaction direction. The mixer converts
 * (throttle, roll, pitch, yaw) into per-motor throttle commands.
 *
 * ── Angle convention (important) ─────────────────────────────────────────
 *   angle 0 deg   = motor is at the NOSE
 *   angle 90 deg  = motor is on the RIGHT
 *   angle 180 deg = motor is at the TAIL
 *   angle 270 deg = motor is on the LEFT
 *   increasing angle = clockwise when looking down at the aircraft from above
 *
 * ── Control input convention (important) ─────────────────────────────────
 *   roll  > 0  = roll RIGHT      (right side goes down)
 *   pitch > 0  = pitch NOSE UP   (tail goes down)
 *   yaw   > 0  = yaw RIGHT       (nose turns clockwise seen from above)
 *   thr        = collective throttle in microseconds (1000..2000)
 *
 * Control inputs are in microseconds of authority at a full-arm motor,
 * so roll = 100 means "the most effective motor moves by 100 us".
 *
 * ── yaw_dir convention ───────────────────────────────────────────────────
 *   yaw_dir = +1 : speeding this motor up yaws the aircraft RIGHT (CW from
 *                  above). This is the motor spinning COUNTER-clockwise.
 *   yaw_dir = -1 : speeding this motor up yaws the aircraft LEFT.
 * If your hexa yaws the wrong way, flip the sign for that motor (command
 * `M<motor>,<angle>,<direction>`), do not rewire it.
 */
#ifndef MIXER_H
#define MIXER_H

#include <stdint.h>

#define MIXER_MOTORS     6
#define MIXER_MIN_US     1000
#define MIXER_MAX_US     2000
#define MIXER_IDLE_US    1000

/* Layout presets */
typedef enum {
    MIXER_PRESET_HEXA_X = 1,   /* 30, 90, 150, 210, 270, 330  (no motor dead ahead) */
    MIXER_PRESET_HEXA_P = 2,   /*  0, 60, 120, 180, 240, 300  (motor dead ahead)   */
    MIXER_PRESET_QUAD_X = 3    /* 45,135, 225, 315 on motors 1..4, 5&6 disabled    */
} mixer_preset_t;

typedef struct {
    int16_t  angle_deg;      /* 0..359, see convention above */
    int8_t   yaw_dir;        /* +1 or -1                     */
    uint8_t  enabled;
    /* Q15 gains, recomputed whenever the geometry changes */
    int32_t  roll_gain;      /* = -sin(angle) * 32767 */
    int32_t  pitch_gain;     /* = -cos(angle) * 32767 */
    int32_t  yaw_gain;       /* =  yaw_dir    * 32767 */
} mixer_motor_t;

/* What the limiter had to do to fit the outputs into [1000,2000] us */
typedef enum {
    MIX_OK       = 0,   /* outputs fit as requested            */
    MIX_SHIFTED  = 1,   /* deltas shifted to fit (throttle changed, attitude kept) */
    MIX_SCALED   = 2    /* control range wider than 1000us: deltas scaled down */
} mixer_limit_t;

typedef struct {
    uint16_t     out[MIXER_MOTORS];   /* microseconds, 1000..2000 */
    mixer_limit_t limit;
    int32_t      thr_used;            /* collective actually applied */
} mixer_result_t;

extern mixer_motor_t mixer_motors[MIXER_MOTORS];

void mixer_init(void);
int  mixer_set_motor(int index, int angle_deg, int yaw_dir);   /* 0 = ok, -1 = bad motor */
int  mixer_set_enabled(int index, int enabled);
void mixer_load_preset(mixer_preset_t preset);
int  mixer_preset_from_char(char c);

/* Geometry persistence in the reserved flash page.
 * mixer_save: 0 = stored, <0 = flash error.
 * mixer_load: 0 = saved geometry restored, -1 = nothing valid stored
 *             (the caller keeps whatever preset it already had). */
int  mixer_save(void);
int  mixer_load(void);

/* Pure mixer maths: computes outputs, touches no hardware. */
void mixer_apply(int32_t thr, int32_t roll, int32_t pitch, int32_t yaw,
                 mixer_result_t *res);

#endif /* MIXER_H */
