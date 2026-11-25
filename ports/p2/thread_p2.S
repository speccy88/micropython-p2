// SPDX-License-Identifier: MIT
.section .text.p2_thread_launch
.global p2_thread_launch
p2_thread_launch:
    // Allocate a free cog in HUBEXEC mode, PTRA = worker C stack base.
    mov r31, #0x30
    setq r0
    coginit r31, ##p2_thread_boot wc
    if_c neg r31, #1
    reta

.section .text.p2_thread_boot
p2_thread_boot:
    setq2 #511
    augs #1
    rdlong $0, #0
    jmp #\p2_thread_worker

.section .text.p2_thread_capture
.global p2_thread_capture
p2_thread_capture:
    // Capture volatile and preserved registers before releasing the GIL.
    setq #31
    wrlong r0, r0
    mov r30, r0
    add r30, #128
    wrlong pa, r30
    add r30, #4
    wrlong pb, r30
    add r30, #4
    wrlong ptrb, r30
    mov r31, ptra
    reta
