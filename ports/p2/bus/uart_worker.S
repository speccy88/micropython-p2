// SPDX-License-Identifier: MIT
// HUBEXEC, no C stack/LUT. All pin outputs belong to this worker cog.
// Layout is checked against uart_slot_t at compile time in uart.c.
.section .text.p2_uart_worker,"ax",@progbits
.balign 4
.global p2_uart_worker
p2_uart_worker:
    mov r0, ptra
    rdlong r1, ptra[1]
    rdlong r2, ptra[2]
    rdlong r3, ptra[3]
    rdlong r4, ptra[4]
    dirl r1
    wrpin r4, r1
    wxpin r3, r1
    dirh r1
    dirl r2
    wrpin #0x7c, r2
    wxpin r3, r2
    dirh r2
    mov r5, #0
    mov r6, #0
    mov r7, #0
    mov r8, #0
    mov r9, #1
    wrlong r9, r0
.Luart_loop:
    testp r1 wc
    if_nc jmp #.Luart_tx
    rdpin r9, r1
    shr r9, #24
    rdlong r10, ptra[6]
    mov r11, r5
    sub r11, r10
    cmp r11, ##256 wc
    if_nc jmp #.Luart_overrun
    mov r11, r5
    and r11, #255
    add r11, #44
    add r11, r0
    wrbyte r9, r11
    add r5, #1
    wrlong r5, ptra[5]
    jmp #.Luart_tx
.Luart_overrun:
    add r8, #1
    wrlong r8, ptra[10]
.Luart_tx:
    tjz r7, #.Luart_tx_idle
    testp r2 wc
    if_nc jmp #.Luart_loop
    mov r7, #0
    wrlong r7, ptra[9]
.Luart_tx_idle:
    rdlong r10, ptra[7]
    cmp r6, r10 wz
    if_z jmp #.Luart_loop
    mov r11, r6
    and r11, #255
    add r11, #300
    add r11, r0
    rdbyte r9, r11
    mov r7, #1
    wrlong r7, ptra[9]
    wypin r9, r2
    waitx #20
    add r6, #1
    wrlong r6, ptra[8]
    jmp #.Luart_loop
