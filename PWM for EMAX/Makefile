##########################################################################################################################
# EMAX ESC Motor Controller — Makefile for STM32C092RC (NUCLEO-C092RC)
# Auto-compatible with STM32CubeCLT GCC toolchain
##########################################################################################################################

# Toolchain — auto-detect CubeCLT or PATH
GCC_BASE ?= /opt/ST/STM32CubeCLT_1.22.0/GNU-tools-for-STM32/bin
CC      = $(GCC_BASE)/arm-none-eabi-gcc
OBJCOPY = $(GCC_BASE)/arm-none-eabi-objcopy
SIZE    = $(GCC_BASE)/arm-none-eabi-size

# Project
TARGET   = PWM_for_EMAX
BUILD_DIR = build

# MCU flags
CPU      = -mcpu=cortex-m0plus -mthumb -mfloat-abi=soft
DEFS     = -DSTM32C092xx -DUSE_FULL_LL_DRIVER
OPT      = -Os

# Include paths
INCLUDES = \
  -ICore/Inc \
  -IDrivers/STM32C0xx_HAL_Driver/Inc \
  -IDrivers/STM32C0xx_HAL_Driver/Inc/Legacy \
  -IDrivers/CMSIS/Device/ST/STM32C0xx/Include \
  -IDrivers/CMSIS/Include

# Linker
LDSCRIPT = STM32C092RCTX_FLASH.ld
LDFLAGS  = $(CPU) -T$(LDSCRIPT) -Wl,--gc-sections --specs=nano.specs --specs=nosys.specs -lgcc

# Sources
C_SOURCES = \
  Core/Src/main.c \
  Core/Src/system_stm32c0xx.c \
  Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_usart.c \
  Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_gpio.c \
  Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_exti.c \
  Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_utils.c \
  Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_rcc.c \
  Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_tim.c

ASM_SOURCES = \
  Drivers/CMSIS/Device/ST/STM32C0xx/Source/Templates/gcc/startup_stm32c092xx.s

# Objects
OBJECTS  = $(addprefix $(BUILD_DIR)/,$(notdir $(C_SOURCES:.c=.o)))
OBJECTS += $(addprefix $(BUILD_DIR)/,$(notdir $(ASM_SOURCES:.s=.o)))
vpath %.c $(sort $(dir $(C_SOURCES)))
vpath %.s $(sort $(dir $(ASM_SOURCES)))

# Rules
all: $(BUILD_DIR)/$(TARGET).elf $(BUILD_DIR)/$(TARGET).bin $(BUILD_DIR)/$(TARGET).hex

$(BUILD_DIR)/%.o: %.c | $(BUILD_DIR)
	$(CC) $(CPU) $(OPT) $(DEFS) $(INCLUDES) -c -o $@ $<

$(BUILD_DIR)/%.o: %.s | $(BUILD_DIR)
	$(CC) $(CPU) -c -o $@ $<

$(BUILD_DIR)/$(TARGET).elf: $(OBJECTS)
	$(CC) $(OBJECTS) $(LDFLAGS) -Wl,-Map=$(BUILD_DIR)/$(TARGET).map -o $@
	$(SIZE) $@

$(BUILD_DIR)/$(TARGET).bin: $(BUILD_DIR)/$(TARGET).elf
	$(OBJCOPY) -O binary $< $@

$(BUILD_DIR)/$(TARGET).hex: $(BUILD_DIR)/$(TARGET).elf
	$(OBJCOPY) -O ihex $< $@

$(BUILD_DIR):
	mkdir -p $@

clean:
	rm -rf $(BUILD_DIR)

# Flash via ST-LINK (POWERDOWN mode — safe, always works)
CLI ?= $(shell find /Applications/STM32CubeIDE.app -name "STM32_Programmer_CLI" 2>/dev/null | head -1)
flash: $(BUILD_DIR)/$(TARGET).bin
	$(CLI) -c port=SWD mode=POWERDOWN -halt -e all -d $< 0x08000000 -v -rst

.PHONY: all clean flash
