// SPDX-License-Identifier: MIT
#ifndef MICROPY_P2_SETJMP_H
#define MICROPY_P2_SETJMP_H
#include <stdint.h>

typedef uint32_t jmp_buf[32];
int setjmp(jmp_buf env) __attribute__((returns_twice));
void longjmp(jmp_buf env, int value) __attribute__((noreturn));
#endif
