# Closed-loop mixer control from the STEVAL-MKI109V3 IMU — research & feasibility

_Investigated 2026-10-07. All hardware facts below were read off this machine
(USB descriptors, MEMS Studio's own config, ST's bundled driver), not assumed._

---

## 1. Verdict up front

| Question | Answer |
|---|---|
| Is closed-loop control **feasible**? | **Yes**, with margin. |
| Using the Mac in the loop? | **No** — a host OS in the control path cannot meet the timing. Demo only. |
| Where must the loop close? | **On the flight controller** (STM32C092RC), sampling this IMU directly. |
| Is the C0 capable? | Yes: ~3–8 % CPU at 500 Hz, 1.9 KB of 30 KB RAM used, pins available. |
| Main constraint | The **sensor bus**, not the CPU. See §5. |

The STEVAL-MKI109V3 is an **evaluation carrier**, not a flight component. Its
value to us is (a) it holds the sensor, (b) MEMS Studio gives an independent
attitude/data reference to validate our own implementation against.

---

## 2. What the board is — evidence

| Property | Value | How it was established |
|---|---|---|
| Board | **STEVAL-MKI109V3** "Professional MEMS tool" (ProfiMEMS) | MEMS Studio ships firmware under `firmware/mems-studio/steval-mki109v3/`, and its config records `LAST_PROFIMEMS_DEVICE` |
| MCU | **STM32F401** | Firmware binary `ProfiF4_MKI109V3_*.bin`; strings `"STM32F401 Temp."`, `"STM32F401_ID hex:"` |
| On-board firmware | `ProfiF4_MKI109V3_V3.73.9` (yours) — MEMS Studio 2.4.1 bundles **V3.79.1** | `~/STMicroelectronics/MEMS Studio/firmware/mems-studio/steval-mki109v3/` |
| USB identity | `0483:5740` **"STM32 Virtual ComPort"**, full-speed (12 Mbps), single CDC-ACM, `bcdDevice=0x0200`, serial `3456345D3333` | `ioreg -p IOUSB -w0 -l` |
| Debugger | **None on the bus.** `st-info --probe` → 0 programmers | MEMS Studio marks every target `stlink: 1`, i.e. it programs **through an external ST-Link** |
| Sensor socket | DIL24 adapter socket | Firmware contains a ~100-part adapter database (LSM6DSV16X, ISM330DHCX, LIS2DUX12, …) |

### 2.1 The connected sensor

MEMS Studio's settings record the exact device, **including the serial port that
is plugged in right now**:

```json
"LAST_PROFIMEMS_DEVICE": "STEVAL-MKI230KA (ISM330IS)",
"LAST_SERIAL_PORT":      "cu.usbmodem3456345D33331"     <-- matches the live port
```

So the DIL24 adapter is **STEVAL-MKI230KA → ISM330IS**: a 6-axis IMU
(3-axis accelerometer + 3-axis gyroscope) with ST's ISPU programmable core.

### 2.2 ISM330IS register facts (from ST's bundled driver)

Source: `/Applications/MEMS Studio.app/Contents/Resources/ProjectTemplate/Drivers/BSP/Components/ism330is/`
— an official ST driver we can reuse rather than re-derive.

| Item | Value |
|---|---|
| `WHO_AM_I` register | **0x0F** |
| Device ID | **0x22** |
| I²C address (7-bit) | **0x6A** (SA0=0) or **0x6B** (SA0=1) |
| `CTRL1_XL` (accel) | 0x10 |
| `CTRL2_G` (gyro) | 0x11 |
| `CTRL3_C` (BDU / IF_INC / SW_RESET / BOOT) | 0x12 |
| `CTRL6_C`, `CTRL7_G` | 0x15, 0x16 |
| Temperature | 0x20–0x21 |
| **Gyro output** | **0x22–0x27** (X/Y/Z, int16 LE) |
| **Accel output** | **0x28–0x2D** (X/Y/Z, int16 LE) |
| Accel FS | 2 / 4 / 8 / 16 g |
| Gyro FS | 125 → 2000 dps |
| ODR | up to **6667 Hz** (HP and LP variants) |

**Why 0x22–0x2D matters:** gyro + accel are *contiguous*, so one 12-byte burst
read from register 0x22 with `IF_INC=1` fetches the whole inertial sample in a
single bus transaction. That is exactly the access pattern a control loop wants.

---

## 3. Protocol reality — what we can and cannot talk to

Tested, not assumed:

| Probe | Result |
|---|---|
| ASCII (`hello`, `\n`, `#` CLI, `help`, `status`) at 115200…921600 | **silent** |
| MSP (Betaflight/INAV framing) | **silent** |
| DTR/RTS asserted, then read | **silent** |
| ST `stdatalog` ASPEP/SSTL beacon @1843200 | **`ASPEPHeaderError` — no response** |

The board speaks ST's **proprietary ProfiMEMS protocol** over the VCP, which is
what MEMS Studio uses. It is not the `FP-SNS-DATALOG2`/SDATALOG `ASPEP` protocol,
so **`stdatalog_core`/`stdatalog_pnpl` cannot be used with this board** — that
stack belongs to the SensorTile.box PRO (PID `5744`), a different device.

Practical consequence: we cannot cheaply stream this IMU from the host. We do
not need to — see §4.

---

## 4. Why the loop must be on the flight controller

Control-loop latency is not about computation, it is about **transport delay**,
and delay eats phase margin:

> phase loss ≈ ω · T_d

| Architecture | Realistic sensor→actuator delay | Phase loss @ 10 Hz crossover | Phase loss @ 40 Hz crossover |
|---|---|---|---|
| **IMU on the C0** (direct bus) | **≈ 0.2–1.0 ms** | 1.3–6° | 5–25° |
| Host in the loop (USB → macOS → Python → UART) | **≈ 5–20 ms, jittery** | 18–72° | 72–288° |

A 40 Hz-crossover rate loop through the host loses **more than the entire usable
phase margin** — it cannot be stabilised with any tuning. Even a slow 10 Hz
angle loop loses ~18–72°, and the *jitter* is worse than the mean, because a
control loop must be tuned for its worst-case delay.

Contributors to host latency: USB full-speed 1 ms frame quantisation, CDC
buffering, macOS scheduler granularity, Python GIL/GC, and two serial hops.
None of these are deterministic.

**Conclusion:** the Mac + MEMS Studio is a *reference and analysis* tool. The
control loop must run on the flight controller, sampling the IMU directly.

---

## 5. Is the STM32C092RC capable? (the real feasibility question)

| Resource | Budget | Need | Verdict |
|---|---|---|---|
| CPU | 48 MHz, 500 Hz loop → **96 000 cycles/iter** | 12-byte read + filter + 3×PID + mixer ≈ 3 000–8 000 cycles | **~3–8 %** ✅ |
| FPU | **none** | fixed-point Q15/Q16 PID | The existing mixer already does exactly this ✅ |
| RAM | 1.9 KB used of 30 KB | filter + PID state < 200 B | ✅ |
| Pins | free: PA0/PA9/PA11/PA12/PA15, PB0–PB7, PB10–PB15, PC0–PC8, PC10–PC15 | 4 (SPI) or 2 (I²C) | ✅ |
| **Bus speed** | **current I²C1 = 100 kHz** | 12 B ≈ **1.4 ms** per read | ❌ **the bottleneck** |

### 5.1 The bottleneck, quantified

A 12-byte read costs roughly 16 bytes on the wire (address+register, restart,
address, 12 data) ≈ 144 bits:

| Bus | Time for one inertial sample | Share of a 2 ms frame |
|---|---|---|
| I²C 100 kHz (today) | ≈ **1.4 ms** | **70 %** ❌ |
| I²C 400 kHz | ≈ 0.36 ms | 18 % ⚠️ acceptable |
| **SPI @ 10 MHz** | ≈ **10 µs** | **~0.5 %** ✅ |

So: **I²C at 100 kHz cannot support this loop.** Two routes:

- **Phase 1 — fast to prove:** share the existing I²C1 (PB8/PB9) with the PMU and
  raise it to 400 kHz. Address-clean: ISM330IS at `0x6A/0x6B`, INA228 at `0x45`,
  INA226 at `0x41` — **no conflict**.
- **Phase 2 — the right end state:** put the IMU on **SPI1/SPI2** (~10 µs,
  deterministic, and off the PMU's bus so the 10 Hz PMU traffic cannot inject
  jitter into the control loop).

⚠️ Note: the phase-1 I²C timing change also affects the PMU path
(`I2C_TIMINGR_VAL` is currently tuned for 100 kHz @48 MHz). The INA228 must be
re-checked at 400 kHz.

### 5.2 Two existing firmware behaviours that must change

1. **The 5 ms soft-start ramp fights a control loop.** `RAMP_INTERVAL_MS 5`
   slews actual CCR toward target for motor protection. A 500 Hz stabiliser
   writing `S`-style targets through that ramp adds up to 5 ms of extra lag —
   more than the whole budget. The stabiliser must write CCR directly (keeping
   the ramp only for the collective/throttle path, or re-tuning it).
2. **The mixer interface already fits.** `mixer_apply(thr, roll, pitch, yaw)`
   takes `roll/pitch/yaw` in **microseconds of authority**, which is exactly the
   natural output unit of a PID. No unit conversion is needed — a PID produced in
   µs plugs straight into the mixer.

---

## 6. Recommended architecture

```
     ┌───────────────── STM32C092RC (flight controller) ─────────────────┐
     │  ISM330IS ──SPI@10MHz──► burst read 0x22..0x2D (12 B)             │
     │                │                                                  │
     │                ▼                                                  │
     │   gyro bias cal ─► fixed-point complementary filter ─► roll/pitch │
     │                                   │                    gyro rate │
     │                                   ▼                              │
     │              rate PID (3 axes, Q15, output in µs)  ─► roll/pitch/yaw
     │                                   │                              │
     │                                   ▼                              │
     │              existing mixer_apply(thr, roll, pitch, yaw) ─► 6×PWM │
     └───────────────────────────────────────────────────────────────────┘
              ▲                                  ▲
              │ UART telemetry (existing)        │ arm / kill / watchdog (existing)
        GroundStation dashboard            Mac + MEMS Studio = INDEPENDENT
        (+ roll/pitch/yaw + gyro)          attitude reference for validation
```

The MKI109V3 stays in the loop **only as an instrument**: mount both, log our
attitude next to ST's, and compare. That is how we validate the filter without
flying.

---

## 7. Implementation plan

| # | Step | Notes |
|---|---|---|
| 1 | **Wire the ISM330KA adapter to the C0** | Recommend removing it from the DIL24 socket and wiring it directly — otherwise the STM32F401 drives the same bus and there is contention. |
| 2 | **Read `WHO_AM_I` (0x0F), expect `0x22`** | Proves wiring + identity in one shot. Do this before anything else. |
| 3 | Port a lean integer-only driver | Reuse the *constants* from ST's `ism330is_reg.h` (already on disk). Init: `BDU=1`, `IF_INC=1`, accel ±4 g, gyro ±500/1000 dps, ODR ≈ 1667 Hz. |
| 4 | Burst read `0x22..0x2D` | One transaction per sample. |
| 5 | Gyro bias calibration at boot | Average N samples while still; store as Q15 bias. The Python stack already proved this is essential (clean 0.00 dps when still). |
| 6 | Fixed-point complementary filter | α≈0.97–0.99, gyro-integrated with accel correction. Yaw gyro-led (the Python stack showed mag-trusting yaw "teleports on tiny noise"). |
| 7 | Rate PID, 3 axes, output in µs | Integer; clamp; anti-windup on the integrator. |
| 8 | Feed `mixer_apply()` | Reuse the existing configurable-geometry mixer unchanged. |
| 9 | Mode gating | Explicit `STABILIZE on/off`. Arm/disarm/kill/watchdog semantics unchanged; kill keeps zeroing the mixer. |
| 10 | Telemetry + dashboard | Publish roll/pitch/yaw + gyro rates; add a small attitude indicator. |
| 11 | Bench verification | Props **off**. Static: attitude matches MEMS Studio. Then disturbance: displace the frame by hand and confirm the rate loop counters it. |
| 12 | Optional | Replace complementary with Mahony/Madgwick; use the ISM330IS FIFO to batch samples and decouple bus timing from loop timing. |

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| **Vibration** — the adapter is hard-mounted, no isolation | Start with LPF; add soft-mounting later. This is the classic cause of a "twitchy" first flight. |
| **Sensor axis remap** | The Python stack already needed `AXIS_ORDER`/`AXIS_SIGN`; expect the same here. Get it right on the bench, not in the air. |
| **I²C shared with the PMU** (phase 1) | Prefer SPI; or accept the 10 Hz PMU traffic as jitter. |
| **100 kHz I²C is inadequate** | Raise to 400 kHz, or use SPI. Must not be skipped. |
| **Ramp vs loop interaction** | Bypass the 5 ms ramp on the stabiliser path (§5.2). |
| **First flight** | The kill path now works from the GUI (`!` / RESET KILL) — keep props off until the bench disturbance test is convincing. |

## 9. Unknowns I could not resolve from the machine

- The exact **pinout of the STEVAL-MKI230KA** adapter (which pads are SCK/MISO/MOSI/CS/VDD/GND) — needed for step 1.
- Whether the MKI109V3 exposes the sensor on a header in a way we could tap without removing the adapter.
- ISM330IS **FIFO depth** and whether **SFLP** (on-sensor quaternion) is available — would be a nice shortcut; worth checking the datasheet before writing our own filter.
- SPI/I²C **AF numbers on the C0 for the chosen pins** — must be checked in UM3353 Table 13 (the same table that gave us I2C1 PB8/PB9 = AF6).

---

## 10. What I need to proceed

1. **Confirm the adapter part number** printed on the small DIL24 board — I
   derived `STEVAL-MKI230KA / ISM330IS` from MEMS Studio's last-used record, which
   is strong but not the same as reading the silk screen.
2. **Plug the NUCLEO-C092RC back in.** It is currently *unplugged* (no ST-Link on
   the bus), so I cannot build/flash/verify anything on the flight controller
   right now.
3. **A decision on wiring:** wire the IMU to **I²C1 @400 kHz** (share with the
   PMU, fastest to get a `WHO_AM_I` answer) or straight to **SPI** (the correct
   end state)?
4. Optional: the STEVAL-MKI230KA pinout or a photo of the board.

With (1) and (2) I can immediately do steps 2–4 (probe, driver, burst read) and
show real samples in the telemetry, which is the point where "feasible" becomes
"demonstrated".
