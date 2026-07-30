ENTRY(Reset_Handler)
MEMORY
{
  FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 256K
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 32K
}
_estack = ORIGIN(RAM) + LENGTH(RAM);
SECTIONS
{
  .isr_vector : { . = ALIGN(4); KEEP(*(.isr_vector)); . = ALIGN(4); } >FLASH
  .text : { . = ALIGN(4); *(.text*); *(.rodata*); . = ALIGN(4); _etext = .; } >FLASH
  .data : { . = ALIGN(4); _sdata = .; *(.data*); . = ALIGN(4); _edata = .; } >RAM AT>FLASH
  _sidata = LOADADDR(.data);
  .bss : { . = ALIGN(4); _sbss = .; *(.bss*); *(COMMON); . = ALIGN(4); _ebss = .; } >RAM
  /DISCARD/ : { *(.ARM.attributes); *(.comment); *(.note*); }
}
