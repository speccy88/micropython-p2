// SPDX-License-Identifier: MIT
// Test-only observer: sample SCK (P8) and MOSI (P9) without driving them.
// P0 must be disconnected and configured as Pin.IN on cog0. The active
// trial raises P0 on the first SCK high to interrupt the actual transfer.
.section .p2driver,"ax",@progbits
.balign 4
.global p2_driver_entry
p2_driver_entry:
    drvl #0
    mov r0, #1
    wrlong r0, ptra
.Lstart:
    rdlong r7, ptra[1]
    tjz r7, #.Lstart
    mov r10, ptra
    add r10, #16
    mov r5, #0
    mov r4, ##0xffffffff
.Lsample:
    mov r2, ina
    getct r3
    shr r2, #8
    and r2, #3
    cmp r2, r4 wz
    if_z jmp #.Lcommand
    mov r4, r2
    test r2, #1 wc
    cmp r7, #2 wz
    if_c_and_z drvh #0
    wrlong r3, r10
    add r10, #4
    wrlong r2, r10
    add r10, #4
    add r5, #1
    cmp r5, #64 wz
    if_z jmp #.Ldone
    wrlong r7, ptra[2]
.Lcommand:
    rdlong r8, ptra[1]
    cmp r7, r8 wz
    if_z jmp #.Lsample
.Ldone:
    wrlong r5, ptra[3]
    mov r8, #3
    wrlong r8, ptra[2]
.Lidle:
    waitx ##16000
    jmp #.Lidle
