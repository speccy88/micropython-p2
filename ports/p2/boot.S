// Adapted from speccy88/tinygo-p2, modern/overlays/tinygo/targets/p2_boot.S.
.section .text.__entry,"ax",@progbits
.global __entry
__entry:
    jmp #\0x10

.section .p2.boot,"ax",@progbits
.global __start0
__start0:
    mov r31, ##__start
    coginit #0, r31

// Every C cog needs its own LUT copy, including the serial service.
.global __start
__start:
    setq2 #511
    augs #1
    rdlong $0, #0
    cogid r0
    cmp r0, #0 wz
    if_z mov ptra, ##_stack_bottom
    if_z mov r31, ##p2_primary_entry
    if_nz mov ptra, ##_serial_stack
    if_nz mov r31, ##p2_console_service
    jmp r31
