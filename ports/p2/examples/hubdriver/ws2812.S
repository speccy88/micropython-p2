// SPDX-License-Identifier: MIT
// WS2812B-V5/W at 160 MHz. P2D1 mailbox words:
// ready, request, completed, status, pin, count, packed GRB[32].
// Each frame owns its payload from publication until completion.
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
    rdlong r6, r0
    cmp r6, r5 wz
    if_z jmp #.Lidle
    mov r5, r6
    rdlong r7, r3
    cmp r7, #40 wc
    if_nc jmp #.Linvalid
    rdlong r8, r4
    tjz r8, #.Linvalid
    cmp r8, #33 wc
    if_nc jmp #.Linvalid
    // Start with a quiet latch interval, including on the very first frame.
    drvl r7
    waitx ##51200
    mov r9, r4
    getct r10
.Lpixel:
    add r9, #4
    rdlong r11, r9
    shl r11, #8
    mov r12, #24
.Lbit:
    shl r11, #1 wc
    mov r13, #48
    if_c mov r13, #104
    // Arm both deadlines before the rising edge. WAITCT->DRV has the
    // same instruction latency for each edge; the 200-cycle grid is fixed.
    addct1 r10, #200
    mov r14, r10
    addct2 r14, r13
    waitct1
    drvh r7
    waitct2
    drvl r7
    djnz r12, #.Lbit
    djnz r8, #.Lpixel
    waitx ##51200
    dirl r7
    mov r6, #0
    jmp #.Ldone
.Linvalid:
    mov r6, #1
.Ldone:
    wrlong r6, r2
    wrlong r5, r1
    jmp #.Lidle
