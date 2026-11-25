// SPDX-License-Identifier: MIT
#include <math.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdint.h>
#include <string.h>

extern int p2_check_registers(jmp_buf env);
extern uint8_t raw_p2_uart_getc(void);
extern void raw_p2_uart_putc(uint8_t c);

static void send(const char *s) {
    while (*s) {
        raw_p2_uart_putc(*s++);
    }
}

static void number(uint32_t n) {
    for (unsigned i = 0; i < 8; ++i) {
        raw_p2_uart_putc("0123456789abcdef"[n >> 28]);
        n <<= 4;
    }
}

static __attribute__((noinline)) unsigned variadic(unsigned first, ...) {
    va_list args;
    va_start(args, first);
    unsigned a = va_arg(args, unsigned);
    double b = va_arg(args, double);
    uint64_t c = va_arg(args, uint64_t);
    unsigned d = va_arg(args, unsigned);
    va_end(args);
    return first == 7 && a == 0x76543210 && b == -2.5 &&
        c == UINT64_C(0xcafed00ddefaced0) && d == 95;
}

struct payload {
    uint32_t x;
    uint8_t y;
    double d;
};

static __attribute__((noinline)) struct payload transform(struct payload p, unsigned delta) {
    p.x += delta;
    p.y ^= (uint8_t)delta;
    p.d *= 2.0;
    return p;
}

static __attribute__((noinline)) void nested(jmp_buf outer) {
    jmp_buf inner;
    int value = setjmp(inner);
    if (value == 0) {
        longjmp(inner, 0);
    }
    longjmp(outer, value == 1 ? -37 : 2);
}

static int check_context(void) {
    jmp_buf env;
    for (unsigned i = 0; i < 32; ++i) {
        int result = setjmp(env);
        if (result == 0) {
            nested(env);
        }
        if (result != -37 || !p2_check_registers(env)) {
            return 0;
        }
    }
    return 1;
}

static int check_memory(uint8_t seed) {
    uint8_t actual[64], expected[64], saved[64];
    for (unsigned i = 0; i < sizeof(saved); ++i) {
        saved[i] = (uint8_t)(i * 59u + seed);
    }
    for (unsigned src = 0; src < 7; ++src) {
        for (unsigned dst = 0; dst < 7; ++dst) {
            for (unsigned len = 0; len <= 37; ++len) {
                for (unsigned i = 0; i < sizeof(saved); ++i) {
                    actual[i] = expected[i] = saved[i];
                }
                for (unsigned i = 0; i < len; ++i) {
                    expected[dst + i] = saved[src + i];
                }
                if (memmove(actual + dst, actual + src, len) != actual + dst ||
                    memcmp(actual, expected, sizeof(actual))) {
                    return 0;
                }
                if (memset(actual + dst, seed, len) != actual + dst) {
                    return 0;
                }
                for (unsigned i = 0; i < len; ++i) {
                    expected[dst + i] = seed;
                }
                if (memcmp(actual, expected, sizeof(actual))) {
                    return 0;
                }
                if (memcpy(actual + dst, saved + src, len) != actual + dst) {
                    return 0;
                }
                for (unsigned i = 0; i < len; ++i) {
                    expected[dst + i] = saved[src + i];
                }
                if (memcmp(actual, expected, sizeof(actual))) {
                    return 0;
                }
            }
        }
    }
    return 1;
}

static __attribute__((noinline)) int32_t quotient(int32_t a, int32_t b) { return a / b; }
static __attribute__((noinline)) int32_t p2_remainder(int32_t a, int32_t b) { return a % b; }
static __attribute__((noinline)) _Bool below(int a, int b) { return a < b; }

int main(void) {
    // The host supplies four fresh bytes, then checks the response and mask.
    send("P2CRT ready\r\n");
    uint32_t challenge = 0;
    for (unsigned i = 0; i < 4; ++i) {
        challenge = (challenge << 8) | raw_p2_uart_getc();
    }
    unsigned mask = 0;
    if (check_context()) { mask |= 1; }
    if (check_memory(challenge)) { mask |= 2; }
    if (variadic(7, 0x76543210u, -2.5, UINT64_C(0xcafed00ddefaced0), 95u)) { mask |= 4; }
    struct payload p = { challenge, 55, -1.25 };
    struct payload q = transform(p, 18);
    if (q.x == challenge + 18 && q.y == (55 ^ 18) && p.y == 55 && q.d == -2.5) { mask |= 8; }
    if (quotient(-1234567, 91) == -13566 && p2_remainder(-1234567, 91) == -61 &&
        quotient(18, -7) == -2 && p2_remainder(18, -7) == 4 &&
        below(-2, 1) && !below(1, -2)) { mask |= 16; }
    if (sqrtf(16.0f) == 4.0f && fabsf(sinf(0.5f) - 0.47942554f) < 0.000001f) { mask |= 32; }
    send("P2CRT ");
    number(challenge);
    raw_p2_uart_putc(' ');
    number(mask);
    send("\r\n");
    return 0;
}
