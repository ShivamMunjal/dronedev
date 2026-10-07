cmake_minimum_required(VERSION 3.20)

# ---------------------------------------------------------------------------
# Bare-metal cross build for STM32F401RE (Nucleo-F401RE).
# No HAL: only the vendored CMSIS device headers in ./cmsis are required.
# ---------------------------------------------------------------------------
set(CMAKE_SYSTEM_NAME       Generic)
set(CMAKE_SYSTEM_PROCESSOR  arm)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

if(NOT CMAKE_C_COMPILER)
  find_program(ARM_GCC arm-none-eabi-gcc REQUIRED)
  set(CMAKE_C_COMPILER ${ARM_GCC})
endif()

project(pmu_pm02d C)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

set(CPU_FLAGS -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard)

add_compile_options(
  ${CPU_FLAGS}
  -ffunction-sections
  -fdata-sections
  -Wall
  -Wextra
  -Wno-unused-parameter)

add_compile_definitions(STM32F401xE)

include_directories(
  ${CMAKE_CURRENT_SOURCE_DIR}/src
  ${CMAKE_CURRENT_SOURCE_DIR}/cmsis
  ${CMAKE_CURRENT_SOURCE_DIR}/cmsis/core)

set(LDSCRIPT ${CMAKE_CURRENT_SOURCE_DIR}/linker/stm32f401re.ld)

add_executable(pmu_pm02d.elf
  src/startup.c
  src/system.c
  src/uart.c
  src/i2c.c
  src/ina2xx.c
  src/main.c)

target_link_options(pmu_pm02d.elf PRIVATE
  ${CPU_FLAGS}
  -T${LDSCRIPT}
  -nostartfiles
  -Wl,--gc-sections
  -Wl,-Map=${CMAKE_CURRENT_BINARY_DIR}/pmu_pm02d.map
  -Wl,--print-memory-usage)

find_program(ARM_OBJCOPY arm-none-eabi-objcopy REQUIRED)
find_program(ARM_SIZE    arm-none-eabi-size    REQUIRED)

add_custom_command(TARGET pmu_pm02d.elf POST_BUILD
  COMMAND ${ARM_OBJCOPY} -O ihex   $<TARGET_FILE:pmu_pm02d.elf> ${CMAKE_CURRENT_BINARY_DIR}/pmu_pm02d.hex
  COMMAND ${ARM_OBJCOPY} -O binary $<TARGET_FILE:pmu_pm02d.elf> ${CMAKE_CURRENT_BINARY_DIR}/pmu_pm02d.bin
  COMMAND ${ARM_SIZE}   $<TARGET_FILE:pmu_pm02d.elf>
  COMMENT "Creating pmu_pm02d.hex / .bin")
