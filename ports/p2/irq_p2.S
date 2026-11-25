// SPDX-License-Identifier: MIT
// TinyGo/P2's gc_p2.S supplies the interrupted-register preservation model.
// The P2 LLVM ABI returns a word in r31, and preserves r0..r29 across calls.
.set P2_IRQ_COG, 0x80
.macro nix_owned_int
    // NIXINT1. Missing mnemonic in the pinned Clang, verified with FlexSpin.
    .long 0xfd604a24
.endm

.section .text.p2_irq_save,"ax",@progbits
.global p2_irq_save
p2_irq_save:
    getbrk r31 wcz
    stalli
    shr r31, #1
    and r31, #1
    reta

.section .text.p2_irq_restore,"ax",@progbits
.global p2_irq_restore
p2_irq_restore:
    test r0, #1 wz
    if_nz stalli
    if_z allowi
    reta

.section .text.p2_irq_native_install,"ax",@progbits
.global p2_irq_native_install
p2_irq_native_install:
    cogid r31
    tjnz r31, #.Linstalled
    setint1 #0
    nix_owned_int
    mov r31, ##p2_irq_stub
    setq #((p2_irq_stub_end-p2_irq_stub)/4-1)
    rdlong $128, r31
    mov ijmp1, #P2_IRQ_COG
.Linstalled:
    reta

.section .text.p2_irq_native_arm,"ax",@progbits
.global p2_irq_native_arm
p2_irq_native_arm:
    setint1 #0
    nix_owned_int
    wrlong r0, ##p2_irq_pin
    mov r31, r1
    shl r31, #6
    or r31, r0
    // SETSE1 clears the previous event latch and selects the new edge.
    setse1 r31
    setint1 #4
    reta

.section .text.p2_irq_native_stop,"ax",@progbits
.global p2_irq_native_stop
p2_irq_native_stop:
    setint1 #0
    nix_owned_int
    setse1 #0
    mov ijmp1, #0
    reta

// This section is stored in HUB and executes from COG $080. All references
// below are absolute HUB addresses. No HUBEXEC fetch, branch or FIFO use.
.section .p2.irq_blob,"ax",@progbits
.balign 4
.global p2_irq_stub
p2_irq_stub:
    setint1 #0
    wrlong r31, ##p2_irq_saved_r31
    getct r31
    wrlong r31, ##p2_irq_timestamp
    rdlong r31, ##p2_irq_pin
    testp r31 wc
    wrc r31
    wrlong r31, ##p2_irq_level
    rdlong r31, ##p2_irq_generation
    wrlong r31, ##p2_irq_pending
    rdlong r31, ##p2_irq_saved_r31
    reti1
.global p2_irq_stub_end
p2_irq_stub_end:

.section .bss.p2_hw_irq,"aw",@nobits
.balign 4
.macro irq_word name
    .global \name
    \name:
    .zero 4
.endm
irq_word p2_irq_saved_r31
irq_word p2_irq_pin
irq_word p2_irq_timestamp
irq_word p2_irq_level
irq_word p2_irq_generation
irq_word p2_irq_pending
