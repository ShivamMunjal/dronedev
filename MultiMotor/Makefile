##########################################################################
# MultiMotor ESC Controller — 6-channel PWM on STM32C092RC
##########################################################################

GCC_BASE ?= /opt/ST/STM32CubeCLT_1.22.0/GNU-tools-for-STM32/bin
CC      = $(GCC_BASE)/arm-none-eabi-gcc
OBJCOPY = $(GCC_BASE)/arm-none-eabi-objcopy
SIZE    = $(GCC_BASE)/arm-none-eabi-size
TARGET  = MultiMotor
BUILD   = build

CPU    = -mcpu=cortex-m0plus -mthumb -mfloat-abi=soft
DEFS   = -DSTM32C092xx -DUSE_FULL_LL_DRIVER
OPT    = -Os

INC    = -ICore/Inc -IDrivers/STM32C0xx_HAL_Driver/Inc -IDrivers/CMSIS/Device/ST/STM32C0xx/Include -IDrivers/CMSIS/Include

CSRC   = Core/Src/main.c Core/Src/system_stm32c0xx.c \
         Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_usart.c \
         Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_gpio.c \
         Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_exti.c \
         Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_utils.c \
         Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_rcc.c \
         Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_tim.c

ASRC   = startup_stm32c092xx.s

OBJ    = $(addprefix $(BUILD)/,$(notdir $(CSRC:.c=.o))) $(addprefix $(BUILD)/,$(notdir $(ASRC:.s=.o)))
vpath %.c $(sort $(dir $(CSRC)))
vpath %.s $(sort $(dir $(ASRC)))

LDSCRIPT = STM32C092RCTX_FLASH.ld
LDFLAGS  = $(CPU) -T$(LDSCRIPT) -Wl,--gc-sections --specs=nano.specs --specs=nosys.specs -lgcc

all: $(BUILD)/$(TARGET).elf $(BUILD)/$(TARGET).bin $(BUILD)/$(TARGET).hex

$(BUILD)/%.o: %.c | $(BUILD)
	$(CC) $(CPU) $(OPT) $(DEFS) $(INC) -c -o $@ $<

$(BUILD)/%.o: %.s | $(BUILD)
	$(CC) $(CPU) -c -o $@ $<

$(BUILD)/$(TARGET).elf: $(OBJ)
	$(CC) $(OBJ) $(LDFLAGS) -Wl,-Map=$(BUILD)/$(TARGET).map -o $@
	$(SIZE) $@

$(BUILD)/$(TARGET).bin: $(BUILD)/$(TARGET).elf
	$(OBJCOPY) -O binary $< $@

$(BUILD)/$(TARGET).hex: $(BUILD)/$(TARGET).elf
	$(OBJCOPY) -O ihex $< $@

$(BUILD):
	mkdir -p $@

clean:
	rm -rf $(BUILD)

CLI ?= $(shell find /Applications/STM32CubeIDE.app -name "STM32_Programmer_CLI" 2>/dev/null | head -1)
flash: $(BUILD)/$(TARGET).bin
	$(CLI) -c port=SWD mode=POWERDOWN -halt -e all -d $< 0x08000000 -v -rst

.PHONY: all clean flash
