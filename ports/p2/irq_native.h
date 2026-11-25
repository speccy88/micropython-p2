// SPDX-License-Identifier: MIT
#pragma once

#include <stdbool.h>
#include <stdint.h>

// Out-of-line calls are compiler memory barriers and do not preserve C/Z.
// Tokens belong to this cog and must be restored in reverse acquisition order.
uint32_t p2_irq_save(void);
void p2_irq_restore(uint32_t token);

// INT1 and SE1 form one exclusive resource on cog0. Call with the cog mask
// held. Use a live, unique owner address; previous is NULL for a free slot or
// the current owner's token for an atomic handoff. Release quiesces the pair.
bool p2_irq_pair_claim(const void *owner, const void *previous);
bool p2_irq_pair_release(const void *owner);

// Registration owner calls these on cog0 with interrupts stalled. Install
// before the first arm. Arm after invalidating/consuming previous pending work.
void p2_irq_native_install(void);
void p2_irq_native_arm(uint32_t pin, uint32_t trigger);
void p2_irq_native_stop(void);

// VM supplies a nonzero generation. ISR publishes it last, after the sample.
extern volatile uint32_t p2_irq_generation;
extern volatile uint32_t p2_irq_pending;
extern volatile uint32_t p2_irq_timestamp;
extern volatile uint32_t p2_irq_level;
