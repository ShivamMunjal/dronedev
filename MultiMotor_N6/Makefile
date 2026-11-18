# MultiMotor_N6 — STM32N657 (NUCLEO-N657X0-Q) firmware build
# FSBL image: everything runs from AXISRAM2 (0x34180400), loaded by the BootROM
# from the on-board Octo-SPI flash. Requires a trusted header before flashing.
#
#   make            -> build/fsbl.elf + build/fsbl.bin
#   make trusted    -> build/FSBL-trusted.bin  (STM32_SigningTool_CLI)
#   make flash      -> sign + write 0x70000000 via MX25UM51245G external loader
#   make monitor    -> 115200 on the ST-LINK VCP

CROSS   ?= arm-none-eabi-
CC      := $(CROSS)gcc
OBJCOPY := $(CROSS)objcopy
SIZE    := $(CROSS)size

CUBE    := CubeN6
HAL     := $(CUBE)/Drivers/STM32N6xx_HAL_Driver
DEV     := $(CUBE)/Drivers/CMSIS/Device/ST/STM32N6xx
CORE    := $(CUBE)/Drivers/CMSIS/Core/Include

CPU     := -mcpu=cortex-m55 -mthumb -mfpu=fpv5-d16 -mfloat-abi=hard
DEFS    := -DUSE_HAL_DRIVER -DSTM32N657xx -DDEBUG
INCS    := -Ifsbl/Inc -I$(HAL)/Inc -I$(DEV)/Include -I$(CORE)

CFLAGS  := $(CPU) -mcmse $(INCS) $(DEFS) -O2 -g3 -Wall -ffunction-sections -fdata-sections -fno-common
LDFLAGS := $(CPU) -Tfsbl/STM32N657X0HXQ_AXISRAM2_fsbl.ld --specs=nano.specs --specs=nosys.specs \
           -Wl,--gc-sections -Wl,-Map=build/fsbl.map --entry=Reset_Handler

SRCS := fsbl/Src/main.c \
        fsbl/Src/stm32n6xx_it.c \
        fsbl/Src/stm32n6xx_hal_msp.c \
        fsbl/Src/system_stm32n6xx_fsbl.c \
        $(HAL)/Src/stm32n6xx_hal.c \
        $(HAL)/Src/stm32n6xx_hal_cortex.c \
        $(HAL)/Src/stm32n6xx_hal_exti.c \
        $(HAL)/Src/stm32n6xx_hal_gpio.c \
        $(HAL)/Src/stm32n6xx_hal_pwr.c \
        $(HAL)/Src/stm32n6xx_hal_pwr_ex.c \
        $(HAL)/Src/stm32n6xx_hal_rcc.c \
        $(HAL)/Src/stm32n6xx_hal_rcc_ex.c \
        $(HAL)/Src/stm32n6xx_hal_dma.c \
        $(HAL)/Src/stm32n6xx_hal_dma_ex.c \
        $(HAL)/Src/stm32n6xx_hal_uart.c \
        $(HAL)/Src/stm32n6xx_hal_uart_ex.c

OBJS := $(patsubst %.c,build/%.o,$(notdir $(SRCS))) build/startup_stm32n657x0hxq_fsbl.o
VPATH := fsbl/Src $(HAL)/Src fsbl

CP      := /opt/ST/STM32CubeCLT_1.22.0/STM32CubeProgrammer/bin
EXTLDR  := $(CP)/ExternalLoader/MX25UM51245G_STM32N6570-NUCLEO.stldr
VCP     := $(shell ls /dev/cu.usbmodem* 2>/dev/null | head -1)

.PHONY: all clean flash trusted monitor size
all: build/fsbl.bin

build/fsbl.elf: $(SRCS) fsbl/startup_stm32n657x0hxq_fsbl.s fsbl/STM32N657X0HXQ_AXISRAM2_fsbl.ld | build
	$(CC) $(CFLAGS) $(SRCS) fsbl/startup_stm32n657x0hxq_fsbl.s $(LDFLAGS) -o $@
	$(SIZE) $@

build/fsbl.bin: build/fsbl.elf
	$(OBJCOPY) -O binary $< $@

build:
	mkdir -p build

trusted: build/FSBL-trusted.bin
build/FSBL-trusted.bin: build/fsbl.bin
	$(CP)/STM32_SigningTool_CLI -bin $< -nk -of 0x80000000 -t fsbl -o $@ -hv 2.3 -dump $@ | tail -5

flash: build/FSBL-trusted.bin
	$(CP)/STM32_Programmer_CLI -c port=SWD mode=UR -el $(EXTLDR) \
	    -w build/FSBL-trusted.bin 0x70000000 -align 4 -v -rst

size: build/fsbl.elf
	$(SIZE) -A build/fsbl.elf | head -20

monitor:
	screen $(VCP) 115200

clean:
	rm -rf build
