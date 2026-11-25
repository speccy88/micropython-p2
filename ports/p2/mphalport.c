// SPDX-License-Identifier: MIT
#include <stdint.h>
#include "py/runtime.h"
#include "py/mphal.h"
#include "py/stream.h"

extern uint32_t raw_p2_uart_buffered(void);
extern uint8_t raw_p2_uart_getc(void);
extern void raw_p2_uart_putc(uint8_t c);
extern volatile int p2_console_interrupt_char;
extern volatile uint32_t p2_console_interrupt_count;
static uint32_t interrupt_seen;

void mp_hal_set_interrupt_char(int c) {
    p2_console_interrupt_char = c;
}

void p2_console_poll_interrupt(void) {
    if (!mp_thread_is_main_thread()) {
        return;
    }
    #if !P2_PROFILE_THREADED
    p2_timer_poll();
    #endif
    uint32_t count = p2_console_interrupt_count;
    if (count != interrupt_seen) {
        interrupt_seen = count;
        if (p2_console_interrupt_char >= 0) {
            mp_sched_keyboard_interrupt();
        }
    }
}

uintptr_t mp_hal_stdio_poll(uintptr_t flags) {
    uintptr_t available = MP_STREAM_POLL_WR;
    if (raw_p2_uart_buffered()) {
        available |= MP_STREAM_POLL_RD;
    }
    return flags & available;
}

int mp_hal_stdin_rx_chr(void) {
    while (!raw_p2_uart_buffered()) {
        mp_event_wait_indefinite();
    }
    return raw_p2_uart_getc();
}

mp_uint_t mp_hal_stdout_tx_strn(const char *data, size_t len) {
    for (size_t i = 0; i < len; ++i) {
        raw_p2_uart_putc((uint8_t)data[i]);
    }
    return len;
}

// GETCT WC latches the low half for the immediately following GETCT.
extern uint64_t p2_cycle_count(void);
#define CYCLES_PER_US (160u)

mp_uint_t mp_hal_ticks_cpu(void) {
    uint32_t count;
    __asm__ volatile ("getct %0" : "=r" (count));
    return count;
}

mp_uint_t mp_hal_ticks_us(void) {
    return (mp_uint_t)(p2_cycle_count() / CYCLES_PER_US);
}

mp_uint_t mp_hal_ticks_ms(void) {
    return (mp_uint_t)(p2_cycle_count() / (1000 * CYCLES_PER_US));
}

uint64_t mp_hal_time_ns(void) {
    // No battery-backed calendar on the base board. LittleFS uses the Unix
    // epoch for an unknown modification time; time.ticks_* remain monotonic.
    return 0;
}

static void delay_cycles(uint64_t cycles) {
    uint64_t start = p2_cycle_count();
    while (p2_cycle_count() - start < cycles) {
        mp_event_handle_nowait();
        #if P2_PROFILE_THREADED
        if (cycles >= 1000 * CYCLES_PER_US) {
            p2_thread_yield();
        }
        #endif
    }
}

void mp_hal_delay_ms(mp_uint_t ms) {
    delay_cycles((uint64_t)ms * (1000 * CYCLES_PER_US));
}

void mp_hal_delay_us(mp_uint_t us) {
    delay_cycles((uint64_t)us * CYCLES_PER_US);
}
