// SPDX-License-Identifier: MIT
// Clang P2 CC: r0..r29 callee-saved, r31 is the single-word result.
// CALLA pushes the return status/PC onto the ascending hub stack. Save a
// copy because intervening calls may overwrite the original stack slot.
.section .text.setjmp
.global setjmp
setjmp:
    mov ptrb, r0
    setq #29
    wrlong r0, ptrb++
    wrlong ptra, ptrb++
    rdlong r30, ptra[-1]
    wrlong r30, ptrb
    mov r31, #0
    reta

.section .text.longjmp
.global longjmp
longjmp:
    mov ptrb, r0
    mov r31, r1 wz
    if_z mov r31, #1
    setq #29
    rdlong r0, ptrb++
    rdlong ptra, ptrb++
    rdlong r30, ptrb
    wrlong r30, ptra[-1]
    reta
