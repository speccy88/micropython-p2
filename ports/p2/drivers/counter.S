// SPDX-License-Identifier: MIT
// HUBEXEC driver protocol v1. No LUT, stack, pins, locks or object pointers.
// PTRA points to {ready, counter, interval_cycles}; the host owns lifetime.
.section .text.p2_counter_driver,"ax",@progbits
.balign 4
.global p2_counter_driver
p2_counter_driver:
    mov r0, ptra
    add r0, #4
    mov r1, r0
    add r1, #4
    rdlong r2, r1
    mov r3, #0
    mov r4, #1
    wrlong r4, ptra
    getct r5
.Lp2_count:
    addct1 r5, r2
    waitct1
    add r3, #1
    wrlong r3, r0
    jmp #.Lp2_count

.section .text.p2_driver_launch,"ax",@progbits
.global p2_driver_launch
// int p2_driver_launch(const void *entry, volatile void *mailbox)
p2_driver_launch:
    mov r31, #0x30
    setq r1
    coginit r31, r0 wc
    if_c neg r31, #1
    reta
