/* Derived from the TinyGo/P2 native ROM loader and LUT contract. */
ENTRY(__entry)
HUB_LIMIT = 0x7c000;
STACK_SIZE = 0x4000;
SECTIONS {
    . = 0;
    .text : {
        KEEP(*(.text.__entry))
        . = 0x14;
        _clkfreq = .; LONG(160000000)
        _clkmode = .; LONG(0x010007f7)
        _dbgbaud = .; LONG(115200)
        . = 0x40;
        KEEP(*(.p2.boot))
        ASSERT(__start0 == 0x40, "ROM jump destination mismatch")
        KEEP(*(cog))
        ASSERT(. <= 0x200, "COG bootstrap exceeds its slot")
        . = 0x200;
        __p2_lut_load_start = .;
        KEEP(*(lut .lut .lut.*))
        __p2_lut_load_end = .;
        ASSERT(__p2_lut_load_end - __p2_lut_load_start <= 0x800, "LUT overflow")
        . = 0xa00;
        *(.text .text.*)
    }
    .rodata : { *(.rodata .rodata.*) }
    .data : { *(.data .data.* .sdata .sdata.*) }
    .bss (NOLOAD) : {
        . = ALIGN(8);
        _bss_start = .;
        *(.bss .bss.* .sbss .sbss.* COMMON)
        . = ALIGN(8);
        _bss_end = .;
    }
    .stack.serial (NOLOAD) : { _serial_stack = .; . += 1024; }
    _heap_start = ALIGN(8);
    _heap_end = HUB_LIMIT - STACK_SIZE;
    .stack HUB_LIMIT - STACK_SIZE (NOLOAD) : {
        _stack_bottom = .;
        . += STACK_SIZE;
        _stack_top = .;
    }
    ASSERT(_heap_start + 32768 <= _heap_end, "P2 requires at least 32 KiB of hub GC arena")
}
