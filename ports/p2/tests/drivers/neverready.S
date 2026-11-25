// SPDX-License-Identifier: MIT
// A valid, idle HUBEXEC program that deliberately omits the ready signal.
.section .p2driver,"ax",@progbits
.balign 4
.global p2_driver_entry
p2_driver_entry:
.Lidle:
    jmp #.Lidle
