##########################################################################
# MultiMotor ESC Controller — 6-channel PWM on STM32C092RC
##########################################################################

GCC_BASE ?= /opt/ST/STM32CubeCLT_1.22.0/GNU-tools-for-STM32/bin
CC      = $(GCC_BASE)/arm-none-eabi-gcc
OBJCOPY = $(GCC_BASE)/arm-none-eabi-objcopy
SIZE    = $(GCC_BASE)/arm-none-eabi-size
TARGET  = MultiMotor
BUILD   = build
.DEFAULT_GOAL := all

CPU    = -mcpu=cortex-m0plus -mthumb -mfloat-abi=soft
DEFS   = -DSTM32C092xx -DUSE_FULL_LL_DRIVER
OPT    = -Os

INC    = -I../IMU/src -I../IMU/Middlewares/MotionFX/Inc -ICore/Inc -IDrivers/STM32C0xx_HAL_Driver/Inc -IDrivers/CMSIS/Device/ST/STM32C0xx/Include -IDrivers/CMSIS/Include

# MotionFX (Cortex-M0+ build) for the IMU fusion path. The IMU project's I2C
# driver is multi-instance so it serves BOTH I2C1 (PMU) and I2C2 (IMU); the
# motor firmware's own i2c.c is dropped in favour of it.
MOTIONFX = ../IMU/Middlewares/MotionFX/Lib/MotionFX_CM0P_wc16_ot.a

CSRC   = Core/Src/main.c Core/Src/system_stm32c0xx.c \
         Core/Src/mixer.c Core/Src/pmu.c Core/Src/ina2xx.c \
         Core/Src/flashcfg.c \
         Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_usart.c \
         Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_gpio.c \
         Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_exti.c \
         Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_utils.c \
         Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_rcc.c \
         Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_tim.c

ASRC   = startup_stm32c092xx.s

# IMU sources are built as their OWN objects, never via $(notdir)+vpath: that
# path collided with the motor project's main.c and i2c.c and silently compiled
# the wrong file (build/main.o became the IMU's main).
IMU_OBJ = $(BUILD)/imu_i2c.o $(BUILD)/ism330is.o $(BUILD)/fusion.o

OBJ    = $(addprefix $(BUILD)/,$(notdir $(CSRC:.c=.o))) $(addprefix $(BUILD)/,$(notdir $(ASRC:.s=.o))) $(IMU_OBJ)
DEPS   = $(OBJ:.o=.d)
vpath %.c $(sort $(dir $(CSRC)))
vpath %.s $(sort $(dir $(ASRC)))

$(BUILD)/imu_i2c.o: ../IMU/src/i2c.c | $(BUILD)
	$(CC) $(CPU) $(OPT) $(DEFS) $(INC) -fshort-wchar -MMD -MP -c -o $@ $<
$(BUILD)/ism330is.o: ../IMU/src/ism330is.c | $(BUILD)
	$(CC) $(CPU) $(OPT) $(DEFS) $(INC) -fshort-wchar -MMD -MP -c -o $@ $<
$(BUILD)/fusion.o: ../IMU/src/fusion.c | $(BUILD)
	$(CC) $(CPU) $(OPT) $(DEFS) $(INC) -fshort-wchar -MMD -MP -c -o $@ $<

LDSCRIPT = STM32C092RCTX_FLASH.ld
# MotionFX is soft-float + 2-byte wchar_t: -lm for its math, --no-warn-mismatch
# for the wchar build difference (we only pass floats across the boundary).
LDFLAGS  = $(CPU) -fshort-wchar -T$(LDSCRIPT) -Wl,--gc-sections -Wl,--no-warn-mismatch --specs=nano.specs --specs=nosys.specs
LDLIBS   = $(MOTIONFX) -lm -lgcc

all: $(BUILD)/$(TARGET).elf $(BUILD)/$(TARGET).bin $(BUILD)/$(TARGET).hex

# -MMD -MP emits one .d file per object listing the headers it included, so
# editing a HEADER actually triggers a rebuild. Without this, changing
# Core/Inc/*.h silently produced stale firmware.
$(BUILD)/%.o: %.c | $(BUILD)
	$(CC) $(CPU) $(OPT) $(DEFS) $(INC) -fshort-wchar -MMD -MP -c -o $@ $<

$(BUILD)/%.o: %.s | $(BUILD)
	$(CC) $(CPU) -c -o $@ $<

$(BUILD)/$(TARGET).elf: $(OBJ)
	$(CC) $(OBJ) $(LDFLAGS) $(LDLIBS) -Wl,-Map=$(BUILD)/$(TARGET).map -o $@
	$(SIZE) $@

$(BUILD)/$(TARGET).bin: $(BUILD)/$(TARGET).elf
	$(OBJCOPY) -O binary $< $@

$(BUILD)/$(TARGET).hex: $(BUILD)/$(TARGET).elf
	$(OBJCOPY) -O ihex $< $@

$(BUILD):
	mkdir -p $@

clean:
	rm -rf $(BUILD)

-include $(DEPS)

CLI ?= $(shell find /Applications/STM32CubeIDE.app -name "STM32_Programmer_CLI" 2>/dev/null | head -1)
flash: $(BUILD)/$(TARGET).bin
	$(CLI) -c port=SWD mode=POWERDOWN -halt -e all -d $< 0x08000000 -v -rst

.PHONY: all clean flash
