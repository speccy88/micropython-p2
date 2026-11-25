// SPDX-License-Identifier: MIT
// Mailbox longs: ready, request, completed, status, count, sum, payload[58].
// Register addresses and relative local branches are position independent.
.section .p2driver,"ax",@progbits
.balign 4
.global p2_driver_entry
p2_driver_entry:
    mov r0, ptra
    add r0, #4
    mov r1, r0
    add r1, #4
    mov r2, r1
    add r2, #4
    mov r3, r2
    add r3, #4
    mov r4, r3
    add r4, #4
    mov r5, #0
    mov r6, #1
    wrlong r6, ptra
.Lidle:
    rdlong r7, r0
    cmp r7, r5 wz
    if_z jmp #.Lidle
    mov r5, r7
    rdlong r8, r3
    mov r9, #0
    mov r6, #0
    cmp r8, #59 wc
    if_nc mov r6, #1
    if_nc jmp #.Ldone
    cmp r8, #0 wz
    if_z jmp #.Ldone
    mov r10, r4
.Lsum:
    add r10, #4
    rdlong r11, r10
    add r9, r11
    sub r8, #1 wz
    if_nz jmp #.Lsum
.Ldone:
    wrlong r9, r4
    wrlong r6, r2
    wrlong r5, r1
    jmp #.Lidle
