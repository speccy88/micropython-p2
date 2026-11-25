// SPDX-License-Identifier: MIT
// Force an unaligned PTRA and keep two live values exclusively in registers.
.section .text.p2_check_registers
.global p2_check_registers
p2_check_registers:
    wrlong r1, ptra++
    setq #1
    wrlong r24, ptra++
    add ptra, #1
    mov r24, ##0x1765ace9
    mov r25, ##0xa6eb3504
    calla #\setjmp
    tjnz r31, #.Lresumed
    mov r24, #0
    mov r25, #0
    mov r1, #9
    calla #\longjmp
.Lresumed:
    cmp r31, #9 wz
    if_z cmp r24, ##0x1765ace9 wz
    if_z cmp r25, ##0xa6eb3504 wz
    mov r31, #0
    if_z mov r31, #1
    sub ptra, #1
    setq #1
    rdlong r24, --ptra
    rdlong r1, --ptra
    reta
