# IMU Ground Station — 3D attitude dashboard

Web dashboard for the **ISM330IS + MotionFX 6X** IMU firmware on the
NUCLEO-C092RC. It shows a live 3D model of the sensor board and, after you
**calibrate** the current pose as zero, the movement you make relative to it
(rotate the board 36° → the readout shows 36°).

## Run

```bash
cd IMU/GroundStation
node server.js            # or: ./start.sh
```
→ open **http://localhost:4100**

The board must be running the IMU firmware (`cd IMU && ./flash.sh`).

## What it does

- Auto-detects the NUCLEO VCP, opens it at 115200.
- Asks the firmware for the **fused attitude stream** (`a`) and keeps asking
  until `E,` lines actually arrive, so it works regardless of boot mode.
- Parses `E,<t>,<roll>,<pitch>,<yaw>,<gbx>,<gby>,<gbz>` (milli-degrees) and
  broadcasts each frame over WebSocket.
- Renders a **craft graphic** that rotates in 3D with the sensor (CSS 3D
  transform driven by roll/pitch/yaw):
  - **📷 IMAGE** — `public/craft.png`, a supplied drone image (white background
    made transparent + cropped) as the default visual,
  - **🛸 HEXA** — a top-down hexacopter SVG with motor angles
    **30/90/150/210/270/330** (matching the firmware's default geometry) and a
    nose marker, which spins cleanly with yaw.
  - Toggle in the corner of the view.
- **CALIBRATE ZERO** averages the last ~0.4 s and makes that pose 0°, so all
  three readouts (and the compass needle) show movement from there.
- **ZERO GYRO (z)** asks the firmware to average 200 samples of gyro bias —
  hold the board still while it runs.
- Diagnostics panel: absolute angles, MotionFX gyro bias, frame count, port,
  and the firmware's `#` log lines.

## Accuracy / limits

- **Roll and pitch** are accelerometer-aided → absolute and drift-free.
- **Yaw** has **no magnetometer** on the ISM330IS, so it is gyro-integration
  only and **drifts slowly**. Great as a short-term rotation reference; not a
  heading. Add a magnetometer to the bus for absolute yaw.

## Protocols

Fused line (firmware → host), angles in milli-degrees:

```
E,<t_ms>,<roll_mdeg>,<pitch_mdeg>,<yaw_mdeg>,<gbx_mdps>,<gby_mdps>,<gbz_mdps>
```

Commands (host → firmware, newline-terminated): `a` fused, `r` raw, `s` scaled,
`x` stop, `z` zero gyro, `?` status.

> The `a` command is reliable because the firmware now has an **interrupt-driven
> RX ring buffer** (see `src/uart.c`); the old polling driver dropped commands
> whenever the 100 Hz stream blocked the main loop.
