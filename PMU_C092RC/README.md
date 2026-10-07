# PM02D battery telemetry — NUCLEO-C092RC (STM32C092RC)

Same job as the `PMU/` project (Holybro PM02D digital power module over I²C),
ported to a different Nucleo board. Verified facts below are sourced, not guessed.

## 1. Wiring (confirms your CN10 pins 3 and 5)

| NUCLEO-C092RC | | PM02D 6-pin I²C cable |
|---|---|---|
| **CN10 pin 3 = PB8** | I2C1_SCL | SCL |
| **CN10 pin 5 = PB9** | I2C1_SDA | SDA |
| CN10 pin 9/10 = GND | GND | GND |

Source: **UM3353** (NUCLEO-C092RC, board MB2046) Table 13 "Pin assignments for
the STM32 on the ST morpho connectors":

```
CN10        Pin name | number | number | Pin name
            PB8      |   3    |   4    | PC1
            PB9      |   5    |   6    | PA3
```

So pins 3 and 5 are **PB8/PB9**, which is exactly I2C1 — the same pin roles as
your F401RE build. PB8/PB9 are also on the Arduino header CN5 (SCL/D15 and
SDA/D14) if that is easier to probe.

Console: **USART2** PA2/PA3 → on-board ST-LINK V2-1 Virtual COM Port.

## 2. Build, flash, watch

```bash
./build.sh     # -> build/pmu_pm02d_c092rc.{elf,hex,bin}
./flash.sh     # ST-Link SWD
```

```bash
screen /dev/cu.usbmodem1102 115200    # exit: Ctrl-A then K
```

The VCP device number changed with the new board (`1102` instead of `1103`) —
check with `ls /dev/cu.usbmodem*`. As before, use `screen`/`picocom`, not `cat`.

## 3. What changed vs the F401RE version

This is not a rebuild — the STM32C0 is a different generation of both the core
and the peripherals, so the low-level layers were rewritten:

| Area | STM32F401RE | STM32C092RC |
|---|---|---|
| Core | Cortex-M4 + FPU (84 MHz from HSI+PLL) | **Cortex-M0+ (ARMv6-M), no FPU**, 48 MHz |
| Clock | PLL 16/336/4, VOS scale 2 | **HSI 48 MHz direct, no PLL**, 1 flash WS |
| I²C | I²C v1 (`CR2/FREQ`, `CCR`, `SR1/SR2`, `DR`) | **I²C v2** (`TIMINGR`, `CR2` command, `ISR`/`ICR`, `TXDR`/`RXDR`) |
| UART | USART v2 (`SR`, `DR`, `BRR`) | **USART v3** (`ISR`, `TDR`, `RDR`, `PRESC`) |
| GPIO clock | `RCC->AHB1ENR` | `RCC->IOPENR` |
| Math | float accumulators | **integer 64-bit** (µA·ms, mW·ms) — no FPU |
| Vector table | 16 + 101 IRQs | 16 + **32** IRQs |
| Memory | 512 KB / 96 KB | **256 KB flash / 30 KB SRAM** |

### Alternate functions (from ST's own NUCLEO-C092RC examples, not guessed)

| Signal | Pins | AF |
|---|---|---|
| USART2_TX/RX | PA2/PA3 | **AF1** |
| I2C1_SCL/SDA | PB8/PB9 | **AF6** |
| I2C1 kernel clock | — | PCLK1 (48 MHz) |

### I²C timing (100 kHz @ 48 MHz kernel clock)

`TIMINGR = 0xB4201113` — derived, not copied:

```
PRESC  = 11  -> t_PRESC = 12/48MHz = 250 ns
SCLL   = 19  -> t_LOW  = 20 * 250 ns = 5.00 us   (standard mode min 4.7 us)
SCLH   = 17  -> t_HIGH = 18 * 250 ns = 4.50 us   (standard mode min 4.0 us)
SCLDEL = 4   -> 1250 ns >= t_r + t_SU;DAT = 1000 + 250 ns
SDADEL = 2   -> 500 ns  >= t_f + t_HD;DAT - t_SU;DAT
             => ~105 kHz, both edges inside spec
```

## 4. AF auto-detection (why this cannot silently fail)

The I²C1 pin AF was taken from ST's examples for this exact board (AF6), but the
firmware does not *depend* on that being right:

```c
i2c_init_with_af(I2C_AF);           /* AF6 */
if (connect_monitor() != 0) {       /* read MFG_ID from the INA2xx      */
    i2c_init_with_af(I2C_AF_ALT);   /* AF7: retry the whole detection  */
    if (connect_monitor() == 0) s_af = I2C_AF_ALT;
}
```

`connect_monitor()` verifies by reading the chip's manufacturer/device ID
(0x5449 / 0x228), not just an address ping, so a wrong AF is detected and
corrected at boot. The banner and bus scan then report the AF that worked.

## 5. Output

```
t_ms,V_V,I_A,P_W,T_C,mAh,Wh
```

Same CSV as the F4 version. `mAh`/`Wh` now come from 64-bit integer
accumulators:

```c
s_charge_uams += (int64_t)s.current_ua * (int64_t)dt_ms;   /* uA*ms  */
s_energy_mwms += (int64_t)s.power_mw   * (int64_t)dt_ms;   /* mW*ms  */
/* display: mAh = uA*ms / 3.6e9 */
uart_print_fixed64(s_charge_uams / 3600000, 3);
```

Keys: `i` re-print info/header, `z` zero the counters, `?` help.

## 6. Layout

```
CMakeLists.txt          cortex-m0plus, -mfloat-abi=soft, no FPU
linker/stm32c092rc.ld   256K flash / 30K SRAM, _estack = 0x20007800
src/startup.c           ARMv6-M vector table (48 slots), fault reporter
src/system.c            HSI 48 MHz, 1 flash WS, 1 ms SysTick
src/uart.c              USART v3 polling + integer/fixed-point formatter
src/i2c.c               I2C v2 master (TIMINGR/CR2/ISR) + bus un-wedge
src/ina2xx.c            INA226/INA228 driver (reused: integer-only already)
src/main.c              telemetry loop, fixed-point accumulators
```

Resource use: **11.2 KB flash (4.3 %), 2.6 KB RAM (8.5 %)**.

## 7. Porting bugs found on hardware (why the F4 code did not just work)

### 7.1 The I²C slave address must be pre-shifted (the real blocker)

The F4 driver wrote the address to the data register as the **on-wire byte**:

```c
/* STM32F4 (I2C v1) - DR holds the address byte, so it gets shifted here */
I2Cx->DR = (uint32_t)((addr7 << 1) | (rw & 1u));
```

I²C v2 has no address byte; the address goes into a **field**, `CR2.SADD`, and it
is easy to assume a field takes the bare 7-bit address. It does not —
**RM0490, I2C_CR2**:

> *"In 7-bit addressing mode (ADD10 = 0): **SADD[7:1] must be written with the
> 7-bit target address** to be sent. Bits SADD[9], SADD[8] and SADD[0] are don't
> care."*

So the shift is still required:

```c
/* STM32C0 (I2C v2) - the address still lives in SADD[7:1] */
#define I2C_SADD(a) (((uint32_t)(a) << 1) & I2C_CR2_SADD)
```

With the unshifted address the controller silently transmitted **0x22 instead of
0x45**, got a NACK, and the only visible symptom was *"no devices found"* — the
code compiled, the pins were driven, the timing was right.

**How it was diagnosed** (worth reusing):

1. The `/I2C line check` reported `pull-up: 1/1` **and** `pull-down: 1/1`.
   The pull-down reading being high proves an *external* pull-up is present, so
   the module was wired correctly and powered — which moved suspicion off the
   wiring and onto the driver.
2. A bus scan that distinguishes **NACK** from **timeout** (it now does) shows
   the controller really is transmitting. "NACKs seen" + "no ACK at any address"
   points straight at a wrong address, not a dead bus.

### 7.2 Everything else that differs

* USART v3: flags in `ISR`, data in `TDR`/`RDR` (the F4 used `SR`/`DR`).
* I²C v2: `TIMINGR` instead of `CCR`/`TRISE`, `CR2` command word, `ICR` to clear
   flags, `TXDR`/`RXDR` for data, and **no `SWRST`** — bus recovery must drive
   PB8/PB9 as GPIO by hand.
* GPIO clock gate is `RCC->IOPENR` (not `AHB1ENR`).
* Cortex-M0+ has **no FPU**, so all float accumulators became 64-bit integer
   fixed point (uA\*ms, mW\*ms).
* Sticky flags must be cleared per transaction, and a failed transfer should
   re-arm the peripheral (`PE` toggle + `TIMINGR`) so one bad transfer cannot
   poison the following ones.

## 8. Notes / caveats

* **30 KB SRAM** is the conservative figure (ST/Zephyr both state 30 KB for this
  board), so the initial stack pointer is 0x20007800. A 36 KB assumption would
  place the stack in invalid memory; 30 KB is safe either way.
* The **Cortex-M0+ has no hardware divide**, so the per-sample int64 divisions
  run in software. At 10 Hz this is irrelevant, but it is why the sample loop
  does not do more maths than necessary.
* `i2c_bus_recover()` drives PB8/PB9 as open-drain GPIO and clocks 9 pulses to
  free a slave stuck holding SDA, then re-enables the peripheral — I²C v2 has no
  `SWRST`, so the pins must be driven manually.
* I²C v2 needs `CR2` written as a whole command word; `START` self-clears and
  writing `START` again is also what clears `TC` for the repeated-start read.
