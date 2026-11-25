// SPDX-License-Identifier: MIT
// Bench fixture only. Leave P0 physically disconnected and use only a
// floating Pin.IN there on cog0. This cog supplies the external stimulus.
// Mailbox words: 1=request, 2=ack, 4=mode, 5=CT just before the edge.
// Mode 4 drives high after the delay in word 6, acknowledging after the edge.
// Modes 5/6 set the fixture's P10 low/high; 7 floats it again. Use only
// during the master's released-SCL START/STOP test on a disconnected pad.
.section .p2driver,"ax",@progbits
.balign 4
.global p2_driver_entry
p2_driver_entry:
    mov r0, #1
    wrlong r0, ptra
    mov r1, #0
    mov r2, #3
.Lpoll:
    rdlong r3, ptra[1]
    cmp r1, r3 wz
    if_nz jmp #.Lchange
    cmp r2, #2 wz
    if_z drvnot #0
    waitx ##1600
    jmp #.Lpoll
.Lchange:
    mov r1, r3
    rdlong r2, ptra[4]
    cmp r2, #4 wz
    if_z rdlong r4, ptra[6]
    if_z waitx r4
    getct r4
    cmp r2, #0 wz
    if_z drvl #0
    cmp r2, #1 wz
    if_z drvh #0
    cmp r2, #4 wz
    if_z drvh #0
    cmp r2, #3 wz
    if_z dirl #0
    cmp r2, #5 wz
    if_z drvl #10
    cmp r2, #6 wz
    if_z drvh #10
    cmp r2, #7 wz
    if_z dirl #10
    wrlong r4, ptra[5]
    wrlong r1, ptra[2]
    jmp #.Lpoll
