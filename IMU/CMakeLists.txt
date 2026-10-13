cmake_minimum_required(VERSION 3.20)

# ---------------------------------------------------------------------------
# Bare-metal cross build for STM32C092RCT6 (NUCLEO-C092RC, board MB2046).
# Cortex-M0+ / ARMv6-M: no FPU, so no -mfpu/-mfloat-abi and no float code.
# ---------------------------------------------------------------------------
set(CMAKE_SYSTEM_NAME       Generic)
set(CMAKE_SYSTEM_PROCESSOR  arm)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

if(NOT CMAKE_C_COMPILER)
  find_program(ARM_GCC arm-none-eabi-gcc REQUIRED)
  set(CMAKE_C_COMPILER ${ARM_GCC})
endif()

project(imu_ism330is_c092rc C)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

set(CPU_FLAGS -mcpu=cortex-m0plus -mthumb -mfloat-abi=soft)

add_compile_options(
  ${CPU_FLAGS}
  -fshort-wchar
  -ffunction-sections
  -fdata-sections
  -Wall
  -Wextra
  -Wno-unused-parameter)

add_compile_definitions(STM32C092xx)

include_directories(
  ${CMAKE_CURRENT_SOURCE_DIR}/src
  ${CMAKE_CURRENT_SOURCE_DIR}/cmsis
  ${CMAKE_CURRENT_SOURCE_DIR}/cmsis/core
  ${CMAKE_CURRENT_SOURCE_DIR}/Middlewares/MotionFX/Inc)

# ST MotionFX (Cortex-M0+ build). Populate with ./setup_motionfx.sh; the .a is
# ST proprietary (SLA0077) so it is intentionally not committed.
set(MOTIONFX_LIB ${CMAKE_CURRENT_SOURCE_DIR}/Middlewares/MotionFX/Lib/MotionFX_CM0P_wc16_ot.a)
if(NOT EXISTS ${MOTIONFX_LIB})
  message(WARNING
    "MotionFX library missing - the fusion build will fail to link.\n"
    "Run ./setup_motionfx.sh to copy it out of an installed MEMS Studio.")
endif()

set(LDSCRIPT ${CMAKE_CURRENT_SOURCE_DIR}/linker/stm32c092rc.ld)

# Make the linker script a real build dependency. Without this, passing it via
# -T is invisible to ninja/make: editing stack size, memory regions or section
# placement leaves a STALE binary in place and `ninja: no work to do`. That is
# how a stack increase silently appeared to have no effect.
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${LDSCRIPT})

add_executable(imu_ism330is_c092rc.elf
  src/startup.c
  src/system.c
  src/uart.c
  src/i2c.c
    src/ism330is.c
  src/fusion.c
  src/main.c)

# MotionFX is soft-float, so it drags in libm/libgcc. Group them AFTER the
# library so the linker can resolve MotionFX's own references to math helpers.
target_link_options(imu_ism330is_c092rc.elf PRIVATE
  ${CPU_FLAGS}
  -fshort-wchar
  # MotionFX_CM0P was built with 2-byte wchar_t; the toolchain's libm with 4.
  # Neither library passes wchar_t across the boundary we use (floats only), so
  # this is cosmetic - silenced rather than left to bury real linker output.
  -Wl,--no-warn-mismatch
  -T${LDSCRIPT}
  -nostartfiles
  -Wl,--gc-sections
  -Wl,-Map=${CMAKE_CURRENT_BINARY_DIR}/imu_ism330is_c092rc.map
  -Wl,--print-memory-usage)

target_link_libraries(imu_ism330is_c092rc.elf
  ${MOTIONFX_LIB}
  m
  gcc)

set_target_properties(imu_ism330is_c092rc.elf PROPERTIES
  LINK_DEPENDS ${LDSCRIPT})

find_program(ARM_OBJCOPY arm-none-eabi-objcopy REQUIRED)
find_program(ARM_SIZE    arm-none-eabi-size    REQUIRED)

add_custom_command(TARGET imu_ism330is_c092rc.elf POST_BUILD
  COMMAND ${ARM_OBJCOPY} -O ihex   $<TARGET_FILE:imu_ism330is_c092rc.elf> ${CMAKE_CURRENT_BINARY_DIR}/imu_ism330is_c092rc.hex
  COMMAND ${ARM_OBJCOPY} -O binary $<TARGET_FILE:imu_ism330is_c092rc.elf> ${CMAKE_CURRENT_BINARY_DIR}/imu_ism330is_c092rc.bin
  COMMAND ${ARM_SIZE}   $<TARGET_FILE:imu_ism330is_c092rc.elf>
  COMMENT "Creating imu_ism330is_c092rc.hex / .bin")
