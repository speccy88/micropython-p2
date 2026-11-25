// SPDX-License-Identifier: MIT
#pragma once
#include <stddef.h>
#include <stdint.h>

// Ticket counters permit a waiting worker to acquire the GIL even while the
// main cog is looping. A single P2 hardware lock protects ticket assignment.
typedef struct {
    volatile uint32_t next;
    volatile uint32_t serving;
} mp_thread_mutex_t;

void p2_thread_init(void);
void p2_thread_stop_other(void);
void p2_thread_gc_other(void);
void p2_thread_yield(void);
