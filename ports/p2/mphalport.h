// SPDX-License-Identifier: MIT
#pragma once
#include "bus/mphal.h"

void mp_hal_set_interrupt_char(int c);
void p2_console_poll_interrupt(void);
#define MICROPY_INTERNAL_EVENT_HOOK p2_console_poll_interrupt()
#if P2_PROFILE_THREADED
void p2_thread_yield(void);
#define MICROPY_INTERNAL_WFE(ms) do { (void)(ms); p2_thread_yield(); } while (0)
#else
#define MICROPY_INTERNAL_WFE(ms) do { (void)(ms); __asm__ volatile ("waitx #128"); } while (0)
#endif
