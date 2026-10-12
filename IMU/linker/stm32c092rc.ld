/*
 * STM32C092RCT6 (NUCLEO-C092RC, board MB2046) linker script
 *   Flash : 256 KB @ 0x08000000
 *   SRAM  :  30 KB @ 0x20000000
 *
 * Note: 30 KB (0x7800) is the conservative figure quoted by ST for this board,
 * so the initial stack pointer is placed at 0x20007800.
 */

ENTRY(Reset_Handler)

_estack = ORIGIN(RAM) + LENGTH(RAM);   /* top of SRAM = initial SP */

_Min_Heap_Size  = 0x200;   /* 512 B */
_Min_Stack_Size = 0x800;   /* 2 KB  */

MEMORY
{
  FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 256K
  RAM   (xrw) : ORIGIN = 0x20000000, LENGTH = 30K
}

SECTIONS
{
  .isr_vector :
  {
    . = ALIGN(4);
    KEEP(*(.isr_vector))
    . = ALIGN(4);
  } >FLASH

  .text :
  {
    . = ALIGN(4);
    *(.text)
    *(.text*)
    *(.rodata)
    *(.rodata*)
    . = ALIGN(4);
    _etext = .;
  } >FLASH

  .ARM.extab : { *(.ARM.extab* .gnu.linkonce.armextab.*) } >FLASH
  .ARM : {
    __exidx_start = .;
    *(.ARM.exidx*)
    __exidx_end = .;
  } >FLASH

  _sidata = LOADADDR(.data);

  .data :
  {
    . = ALIGN(4);
    _sdata = .;
    *(.data)
    *(.data*)
    . = ALIGN(4);
    _edata = .;
  } >RAM AT> FLASH

  .bss :
  {
    . = ALIGN(4);
    _sbss = .;
    __bss_start__ = _sbss;
    *(.bss)
    *(.bss*)
    *(COMMON)
    . = ALIGN(4);
    _ebss = .;
    __bss_end__ = _ebss;
  } >RAM

  /* Reserve heap + stack so an overflow cannot silently corrupt .bss */
  ._user_heap_stack :
  {
    . = ALIGN(8);
    _end = .;
    . = . + _Min_Heap_Size;
    . = . + _Min_Stack_Size;
    . = ALIGN(8);
  } >RAM

  /DISCARD/ : { *(.note.GNU-stack) *(.gnu_debuglink) }
}
