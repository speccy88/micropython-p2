// SPDX-License-Identifier: MIT
// Test-only cog0 code; irq_context has finished using $120 when this runs.
// Args: 0 = WAITX, 1 = REP; output = seven 32-bit words. Returns stalled.
.section .text.irq_block_test,"ax",@progbits
.global irq_block_test
irq_block_test:
    stalli
    setq #8
    wrlong r0, ptra++
    mov r31, ##.Lblock
    setq #((.Lend-.Lblock)/4-1)
    rdlong $288, r31
    mov r31, #288
    call r31
    setq #8
    rdlong r0, --ptra
    reta

.Lblock:
    setint1 #0
    pollct1 wc
    mov r7, #0
    // Both paths start within a handful of instructions of setting CT1.
    cmp r0, #0 wz
    getct r3 wc
    getct r2
    mov r4, r2
    addct1 r4, #128
    setint1 #1
    allowi
    if_z waitx ##2048
    if_nz rep #1, #256
    if_nz add r7, #1
    // Give a deferred IRQ a few interruptible instructions to enter.
    mov r8, #8
.Ldrain:
    djnz r8, #.Ldrain
    getct r6 wc
    getct r5
    stalli
    setint1 #0
    mov r8, iret1
    setq #6
    wrlong r2, r1
    ret
.Lend:
