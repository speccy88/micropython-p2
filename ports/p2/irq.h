// SPDX-License-Identifier: MIT
#pragma once
#include "py/obj.h"

enum { P2_IRQ_RISING = 1, P2_IRQ_FALLING = 2 };
extern const mp_obj_fun_builtin_var_t p2_pin_irq_obj;
extern const mp_obj_fun_builtin_fixed_t p2_disable_irq_obj, p2_enable_irq_obj;
unsigned p2_irq_pin_number(mp_obj_t self);
void p2_irq_pin_detach(mp_obj_t self);
void p2_irq_schedule(uint32_t generation);
void p2_irq_reset(void);
