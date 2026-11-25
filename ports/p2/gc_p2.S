// SPDX-License-Identifier: MIT
// P2 LLVM register convention and GETCT sequence from speccy88/tinygo-p2.
.section .text.p2_cycle_count
.global p2_cycle_count
p2_cycle_count:
    getct r31 wc
    getct r30
    reta

.section .text.p2_stack_pointer
.global p2_stack_pointer
p2_stack_pointer:
    mov r31, ptra
    reta

.section .text.gc_collect
.global gc_collect
gc_collect:
    // Capture before C uses any registers. No Python runs in driver cogs.
    setq #31
    wrlong r0, ##p2_gc_registers
    wrlong ptrb, ##p2_gc_registers+128
    wrlong pa, ##p2_gc_registers+132
    wrlong pb, ##p2_gc_registers+136
    wrlong ptra, ##p2_gc_registers+140
    jmp #\p2_gc_collect_saved

#if P2_TEST_GC_ROOTS
// Return a bit mask for register-only survival, odd-slot survival, and an
// unreferenced control being swept. The PASM caller controls all live roots.
.section .text.p2_gc_test_roots
.global p2_gc_test_roots
p2_gc_test_roots:
    setq #5
    wrlong r0, ptra++
    mov r5, ptra
    add ptra, #12
    mov r4, r5
    add r4, #3
    andn r4, #3
    add r4, #1
    mov r0, #48
    mov r1, #0
    calla #\gc_alloc
    tjz r31, #.Lroots_oom
    mov r2, r31
    mov r0, #64
    calla #\gc_alloc
    tjz r31, #.Lroots_oom
    // Encode bytes explicitly since the test slot is intentionally unaligned.
    mov ptrb, r4
    rep #2, #4
    wrbyte r31, ptrb++
    shr r31, #8
    mov r0, #80
    calla #\gc_alloc
    tjz r31, #.Lroots_oom
    not r3, r31
    mov r30, #0
    mov r31, #0
    mov pa, #0
    mov pb, #0
    mov ptrb, #0
    calla #\gc_collect
    mov r0, r2
    mov r2, #0
    calla #\gc_nbytes
    cmp r31, #48 wz
    if_z or r2, #1
    mov r0, #0
    mov ptrb, r4
    add ptrb, #4
    rep #3, #4
    shl r0, #8
    rdbyte r30, --ptrb
    or r0, r30
    calla #\gc_nbytes
    cmp r31, #64 wz
    if_z or r2, #2
    not r0, r3
    calla #\gc_nbytes
    cmp r31, #0 wz
    if_z or r2, #4
    mov r31, r2
    jmp #.Lroots_done
.Lroots_oom:
    mov r31, #0
.Lroots_done:
    mov ptra, r5
    sub ptra, #24
    setq #5
    rdlong r0, ptra
    reta
#endif
