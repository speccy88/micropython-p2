// SPDX-License-Identifier: MIT
// Standalone acceptance only. Probe runs from COG $120 so its own instruction
// fetches cannot commandeer the foreground FIFO. Use the production ISR at $080.
// Test-only registers $120..$1cf are independent of both runtime scratch and ABI.
.section .text.irq_context
.global irq_context
irq_context:
    setq #12
    wrlong r0, ptra++
    mov r31, ##.Lprobe
    setq #((.Lend-.Lprobe)/4 - 1)
    rdlong $288, r31
    mov r31, #288
    call r31
    setq #12
    rdlong r0, --ptra
    reta

.Lprobe:
    // r0 carries 0 (cost control) or 1 (CT1 interrupt).
    stalli
    setint1 #0
    pollct1 wc
    mov pa, ##0x123abcde
    mov pb, ##0x16543ebc
    mov ptrb, ##0x44443333
    mov r1, ##irq_fifo_data
    rdfast #0, r1
    rflong r2
    mov r1, ##irq_bench_words
    getct r3
    mov r4, r3
    addct1 r4, #184
    setint1 r0
    mov r0, ##0xba1ca110
    mov r31, ##0xc0ffee31
    mov r7, ptra
    mov r8, #150
    cmp r8, #151 wcz
    allowi
    qdiv ##65537, #13
.Lspin:
    djnz r8, #.Lspin
    getct r5
    wrc r8
    wrz r9
    getqx r10
    getqy r11
    rflong r12
    stalli
    setint1 #0
    sub r5, r3
    mov r3, ptra
    sub r3, r7
    wrlong r5, r1
    add r1, #4
    wrlong r4, r1
    add r1, #4
    wrlong r0, r1
    add r1, #4
    wrlong r31, r1
    add r1, #4
    wrlong pa, r1
    add r1, #4
    wrlong pb, r1
    add r1, #4
    wrlong ptrb, r1
    add r1, #4
    wrlong r3, r1
    add r1, #4
    wrlong r8, r1
    add r1, #4
    wrlong r9, r1
    add r1, #4
    wrlong r10, r1
    add r1, #4
    wrlong r11, r1
    add r1, #4
    wrlong r2, r1
    add r1, #4
    wrlong r12, r1
    ret
.Lend:
