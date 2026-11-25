// SPDX-License-Identifier: MIT
// Bootable RAM-only CT1/context fixture. All cycle counts are at 160 MHz.
#include "irq_native.h"
#include <string.h>

extern uint8_t raw_p2_uart_getc(void);
extern void raw_p2_uart_putc(uint8_t);
extern void irq_context(unsigned enabled);
const uint32_t irq_fifo_data[] = {0x61ff8893, 0x42ac6be7};
volatile uint32_t irq_bench_words[14];

static void send(const char *s) {
    while (*s) {
        raw_p2_uart_putc(*s++);
    }
}

static void hex(uint32_t value) {
    raw_p2_uart_putc(' ');
    for (unsigned i = 0; i < 8; ++i) {
        raw_p2_uart_putc("0123456789abcdef"[value >> 28]);
        value <<= 4;
    }
}

static void arm_ct(unsigned delay) {
    unsigned ct;
    __asm__ volatile ("pollct1 wc\n\tgetct %0\n\taddct1 %0, %1\n\tsetint1 #1"
        : "=&r" (ct) : "r" (delay) : "memory", "cc");
}

static __attribute__((noinline)) int nesting(void) {
    __asm__ volatile ("allowi" ::: "memory");
    unsigned outer = p2_irq_save();
    unsigned inner = p2_irq_save();
    arm_ct(160);
    __asm__ volatile ("waitx ##500" ::: "memory");
    unsigned inside = p2_irq_pending;
    p2_irq_restore(inner);
    __asm__ volatile ("waitx ##500" ::: "memory");
    unsigned between = p2_irq_pending;
    p2_irq_restore(outer);
    __asm__ volatile ("waitx ##500" ::: "memory");
    unsigned after = p2_irq_pending;
    send("NEST");
    hex(outer);
    hex(inner);
    hex(inside);
    hex(between);
    hex(after);
    send("\r\n");
    return outer == 0 && inner == 1 && !inside && !between && after == p2_irq_generation;
}

static __attribute__((noinline)) int context(void) {
    static const uint32_t expected[] = {
        0xba1ca110, 0xc0ffee31, 0x123abcde, 0x16543ebc, 0x44443333, 0, 1, 0,
        65537 / 13, 65537 % 13, 0x61ff8893, 0x42ac6be7,
    };
    for (unsigned trial = 0; trial < 8; ++trial) {
        for (unsigned active = 0; active < 2; ++active) {
            p2_irq_pending = 0;
            irq_context(active);
            for (unsigned i = 0; i < sizeof(expected) / sizeof(*expected); ++i) {
                if (irq_bench_words[i + 2] != expected[i]) {
                    send("CONTEXT_MISMATCH");
                    hex(i + 2);
                    hex(irq_bench_words[i + 2]);
                    hex(expected[i]);
                    send("\r\n");
                    return 0;
                }
            }
            if (p2_irq_pending != (active ? p2_irq_generation : 0)) {
                send("PENDING_MISMATCH");
                hex(active);
                hex(p2_irq_pending);
                send("\r\n");
                return 0;
            }
            send(active ? "WITH" : "CONTROL");
            hex(irq_bench_words[0]);
            if (active) {
                hex(p2_irq_timestamp - irq_bench_words[1]);
            }
            send("\r\n");
        }
    }
    return 1;
}

static uint8_t actual[800], initial[800];

extern void irq_block_test(unsigned mode, uint32_t words[7]);
extern uint64_t __udivdi3(uint64_t dividend, uint64_t divisor);

static __attribute__((noinline)) int blocked_service(void) {
    static uint32_t w[7];
    for (unsigned mode = 0; mode < 2; ++mode) {
        for (unsigned i = 0; i < 3; ++i) {
            p2_irq_pending = 0;
            irq_block_test(mode, w);
            const uint64_t start = ((uint64_t)w[1] << 32) | w[0];
            const uint64_t end = ((uint64_t)w[4] << 32) | w[3];
            const uint32_t latency = p2_irq_timestamp - w[2];
            send(mode ? "REP_CT" : "WAITX_CT");
            hex(latency);
            hex(end - start);
            hex(w[5]);
            send("\r\n");
            if (p2_irq_pending != p2_irq_generation || w[2] - w[0] != 128
                || latency < (mode ? 384u : 1920u) || end < start || end - start > 4096
                || latency + 128 > end - start || w[5] != (mode ? 256u : 0)) {
                return 0;
            }
        }
    }
    // Read the return PC retained in IRET1 to prove the interrupt arrived
    // inside the production arithmetic helper executing in the LUT.
    unsigned in_lut = 0;
    for (unsigned delay = 64; delay <= 224; delay += 32) {
        p2_irq_pending = 0;
        arm_ct(delay);
        __asm__ volatile ("allowi" ::: "memory");
        uint64_t q = __udivdi3(0xfedcba9876543210ULL, 0x123456789ULL);
        unsigned pc;
        __asm__ volatile ("stalli\n\tsetint1 #0\n\tmov %0, iret1" : "=r" (pc) : : "memory");
        if (q != 0xfedcba9876543210ULL / 0x123456789ULL) {
            return 0;
        }
        pc &= 0xfffff;
        if (p2_irq_pending == p2_irq_generation && pc >= 0x200 && pc < 0x400) {
            ++in_lut;
        }
    }
    send("LUT_INTERRUPTS");
    hex(in_lut);
    send("\r\n");
    return in_lut > 0;
}

static __attribute__((noinline)) int memory(void) {
    static const unsigned sizes[] = {0, 3, 37, 511, 512, 513, 769};
    unsigned delivered = 0;
    for (unsigned i = 0; i < sizeof(initial); ++i) {
        initial[i] = (uint8_t)(31 * i + (i >> 5));
    }
    for (unsigned i = 0; i < sizeof(sizes) / sizeof(*sizes); ++i) {
        unsigned n = sizes[i];
        for (unsigned src = 0; src < 4; ++src) {
            for (unsigned dst = 0; dst < 4; ++dst) {
                memcpy(actual, initial, sizeof(actual));
                p2_irq_pending = 0;
                arm_ct(96);
                __asm__ volatile ("allowi" ::: "memory");
                memmove(actual + dst, actual + src, n);
                __asm__ volatile ("stalli\n\tsetint1 #0" ::: "memory");
                delivered += p2_irq_pending == p2_irq_generation;
                for (unsigned j = 0; j < sizeof(actual); ++j) {
                    unsigned pos = j >= dst && j - dst < n ? j - dst + src : j;
                    if (actual[j] != initial[pos]) {
                        send("MEMORY_MISMATCH");
                        hex(n);
                        hex(src);
                        hex(dst);
                        hex(j);
                        send("\r\n");
                        return 0;
                    }
                }
            }
        }
    }
    send("MEMORY_INTERRUPTS");
    hex(delivered);
    send("\r\n");
    return delivered > 0;
}

void main(void) {
    while (raw_p2_uart_getc() != '?') {
    }
    send("IRQ_NATIVE_BEGIN\r\n");
    p2_irq_save();
    p2_irq_native_install();
    p2_irq_generation = 39;
    int ok = nesting() && context() && blocked_service() && memory();
    p2_irq_native_stop();
    send(ok ? "IRQ_NATIVE_PASS\r\n" : "IRQ_NATIVE_FAIL\r\n");
}
