cmake_minimum_required(VERSION 3.20)

# Toolchain: use arm-none-eabi-gcc from STM32CubeIDE
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)

set(TOOLCHAIN_PREFIX arm-none-eabi-)

# Find GCC from STM32CubeIDE or PATH
set(STM32CUBE_GCC_PATH "/Applications/STM32CubeIDE.app/Contents/Eclipse/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.macosaarch64_1.0.0.202602081740/tools/bin")

if(EXISTS "${STM32CUBE_GCC_PATH}/${TOOLCHAIN_PREFIX}gcc")
    set(TOOLCHAIN_BIN_DIR "${STM32CUBE_GCC_PATH}")
else()
    find_program(ARM_GCC ${TOOLCHAIN_PREFIX}gcc)
    if(ARM_GCC)
        get_filename_component(TOOLCHAIN_BIN_DIR ${ARM_GCC} DIRECTORY)
    else()
        message(FATAL_ERROR "arm-none-eabi-gcc not found")
    endif()
endif()

set(CMAKE_C_COMPILER   "${TOOLCHAIN_BIN_DIR}/${TOOLCHAIN_PREFIX}gcc")
set(CMAKE_CXX_COMPILER "${TOOLCHAIN_BIN_DIR}/${TOOLCHAIN_PREFIX}g++")
set(CMAKE_ASM_COMPILER "${TOOLCHAIN_BIN_DIR}/${TOOLCHAIN_PREFIX}gcc")
set(CMAKE_AR           "${TOOLCHAIN_BIN_DIR}/${TOOLCHAIN_PREFIX}ar")
set(CMAKE_OBJCOPY      "${TOOLCHAIN_BIN_DIR}/${TOOLCHAIN_PREFIX}objcopy")
set(CMAKE_OBJDUMP      "${TOOLCHAIN_BIN_DIR}/${TOOLCHAIN_PREFIX}objdump")
set(CMAKE_SIZE         "${TOOLCHAIN_BIN_DIR}/${TOOLCHAIN_PREFIX}size")

set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

project(PWM_for_EMAX C ASM)

set(CMAKE_C_STANDARD 11)

# MCU flags
set(MCU_FLAGS "-mcpu=cortex-m0plus -mthumb -mfloat-abi=soft")
set(COMMON_FLAGS "${MCU_FLAGS} -Wall -fdata-sections -ffunction-sections")

set(CMAKE_C_FLAGS "${COMMON_FLAGS}" CACHE STRING "" FORCE)
set(CMAKE_ASM_FLAGS "${MCU_FLAGS} -x assembler-with-cpp" CACHE STRING "" FORCE)
set(CMAKE_EXE_LINKER_FLAGS "${MCU_FLAGS} -Wl,--gc-sections -Wl,-Map=${PROJECT_NAME}.map --specs=nano.specs --specs=nosys.specs" CACHE STRING "" FORCE)

# Defines
add_definitions(
    -DUSE_HAL_DRIVER
    -DSTM32C092xx
    -DUSE_NUCLEO_C092RC
)

# Include paths
include_directories(
    Core/Inc
    Drivers/STM32C0xx_HAL_Driver/Inc
    Drivers/STM32C0xx_HAL_Driver/Inc/Legacy
    Drivers/CMSIS/Device/ST/STM32C0xx/Include
    Drivers/CMSIS/Include
    Drivers/BSP/STM32C0xx_Nucleo
)

# HAL sources (only what we need)
set(HAL_SOURCES
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_cortex.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_rcc.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_rcc_ex.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_gpio.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_dma.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_dma_ex.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_pwr.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_pwr_ex.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_flash.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_flash_ex.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_exti.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_tim.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_tim_ex.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_uart.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_uart_ex.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_usart.c
    Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_usart_ex.c
)

set(BSP_SOURCES
    Drivers/BSP/STM32C0xx_Nucleo/stm32c0xx_nucleo.c
)

set(CORE_SOURCES
    Core/Src/main.c
    Core/Src/stm32c0xx_hal_msp.c
    Core/Src/stm32c0xx_it.c
    Core/Src/system_stm32c0xx.c
)

set(STARTUP_SOURCE
    Drivers/CMSIS/Device/ST/STM32C0xx/Source/Templates/gcc/startup_stm32c092xx.s
)

add_executable(${PROJECT_NAME}.elf
    ${CORE_SOURCES}
    ${HAL_SOURCES}
    ${BSP_SOURCES}
    ${STARTUP_SOURCE}
)

target_link_options(${PROJECT_NAME}.elf PRIVATE "LINKER:-T,${CMAKE_SOURCE_DIR}/STM32C092RCTx_FLASH.ld")

# Generate .hex and .bin after build
add_custom_command(TARGET ${PROJECT_NAME}.elf POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -O ihex $<TARGET_FILE:${PROJECT_NAME}.elf> ${PROJECT_NAME}.hex
    COMMAND ${CMAKE_OBJCOPY} -O binary $<TARGET_FILE:${PROJECT_NAME}.elf> ${PROJECT_NAME}.bin
    COMMAND ${CMAKE_SIZE} $<TARGET_FILE:${PROJECT_NAME}.elf>
    COMMENT "=== Build complete: .elf .hex .bin ==="
)
