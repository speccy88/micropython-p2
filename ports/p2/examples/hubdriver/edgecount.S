// SPDX-License-Identifier: MIT
// Count rising edges on a Smart Pin. Words 0..3 use the P2D1 header;
// words 4..6 are the claimed pin, A-input selector and latest count.
.section .p2driver,"ax",@progbits
.balign 4
.global p2_driver_entry
p2_driver_entry:
    mov r0, #1
    wrlong r0, ptra
.Lsetup:
    rdlong r1, ptra[1]
    tjz r1, #.Lsetup
    rdlong r2, ptra[4]
    rdlong r3, ptra[5]
    cmp r2, #40 wc
    if_nc jmp #.Linvalid
    cmp r3, #8 wc
    if_nc jmp #.Linvalid
    cmp r3, #4 wz
    if_z jmp #.Linvalid
    shl r3, #28
    or r3, #0x1c
    dirl r2
    wrpin r3, r2
    wxpin #0, r2
    wypin #0, r2
    dirh r2
    wrlong r1, ptra[2]
.Lsample:
    rqpin r4, r2
    wrlong r4, ptra[6]
    waitx ##1600
    jmp #.Lsample
.Linvalid:
    mov r4, #1
    wrlong r4, ptra[3]
    wrlong r1, ptra[2]
.Lpark:
    waitx ##160000
    jmp #.Lpark
