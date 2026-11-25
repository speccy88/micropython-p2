// SPDX-License-Identifier: MIT
#include "py/runtime.h"
#include "py/mperrno.h"
#include "drivers/p2resources.h"
#include "irq.h"
#include "irq_native.h"

// Each VM binding has a fresh identity. A stale scheduler argument keeps its
// generation alive until it is drained. A native owner can claim the same
// resource without a Python object or a VM root.
typedef struct {
    mp_obj_base_t base;
    mp_obj_t pin;
    mp_obj_t handler;
    uint32_t service_ct;
    uint8_t number;
    uint8_t trigger;
    uint8_t level;
    bool delivered;
} p2_pin_irq_t;
MP_REGISTER_ROOT_POINTER(void *p2_active_pin_irq);
#define ACTIVE_IRQ ((p2_pin_irq_t *)MP_STATE_PORT(p2_active_pin_irq))
static const mp_obj_type_t p2_pin_irq_type;
static const void *pair_owner;

static bool change_owner(const void *previous, const void *next) {
    if (!p2_on_vm_cog() || pair_owner != previous || (next && p2_vm_resetting)) {
        return false;
    }
    if (previous) {
        p2_irq_native_stop();
        p2_irq_generation = 0;
        p2_irq_pending = 0;
        p2_pin_irq_t *reg = ACTIVE_IRQ;
        if (previous == reg) {
            // Release all Python references only after production has stopped.
            MP_STATE_PORT(p2_active_pin_irq) = NULL;
            reg->handler = MP_OBJ_NULL;
            reg->pin = MP_OBJ_NULL;
        }
    }
    pair_owner = next;
    return true;
}

bool p2_irq_pair_claim(const void *owner, const void *previous) {
    return owner && change_owner(previous, owner);
}

bool p2_irq_pair_release(const void *owner) {
    return owner && change_owner(owner, NULL);
}

static mp_obj_t irq_info(mp_obj_t self_in) {
    if (!mp_obj_is_type(self_in, &p2_pin_irq_type)) {
        mp_raise_TypeError(MP_ERROR_TEXT("PinIRQ required"));
    }
    p2_pin_irq_t *self = MP_OBJ_TO_PTR(self_in);
    if (!self->delivered) {
        return mp_const_none;
    }
    // Snapshot before allocating the tuple or an unsigned 32-bit Python int.
    uint8_t level = self->level;
    uint32_t ct = self->service_ct;
    mp_obj_t result[] = {
        MP_OBJ_NEW_SMALL_INT(self->trigger), MP_OBJ_NEW_SMALL_INT(level), mp_obj_new_int_from_uint(ct),
    };
    return mp_obj_new_tuple(MP_ARRAY_SIZE(result), result);
}
static MP_DEFINE_CONST_FUN_OBJ_1(irq_info_obj, irq_info);
static const mp_rom_map_elem_t irq_locals[] = {
    {MP_ROM_QSTR(MP_QSTR_info), MP_ROM_PTR(&irq_info_obj)},
};
static MP_DEFINE_CONST_DICT(irq_dict, irq_locals);
static MP_DEFINE_CONST_OBJ_TYPE(p2_pin_irq_type, MP_QSTR_PinIRQ, MP_TYPE_FLAG_NONE, locals_dict, &irq_dict);

void p2_irq_pin_detach(mp_obj_t pin) {
    p2_pin_irq_t *reg = ACTIVE_IRQ;
    if (reg && reg->pin == pin) {
        uint32_t state = p2_irq_save();
        p2_irq_pair_release(reg);
        p2_irq_restore(state);
    }
}

void p2_irq_reset(void) {
    uint32_t state = p2_irq_save();
    p2_irq_pair_release(pair_owner);
    p2_irq_restore(state);
}

static mp_obj_t deliver(mp_obj_t token) {
    p2_pin_irq_t *reg = MP_OBJ_TO_PTR(token);
    if (ACTIVE_IRQ == reg && !p2_vm_resetting) {
        // No new ISR can publish until we rearm. Finish the hardware work
        // before calling user code, which can raise, release, or replace us.
        reg->level = p2_irq_level;
        reg->service_ct = p2_irq_timestamp;
        reg->delivered = true;
        uint32_t state = p2_irq_save();
        p2_irq_native_arm(reg->number, reg->trigger);
        p2_irq_restore(state);
        mp_call_function_1(reg->handler, reg->pin);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(deliver_obj, deliver);

void p2_irq_schedule(uint32_t generation) {
    // Only called when the ISR's publication word is nonzero. A full queue
    // leaves the record intact and its source disarmed for the next poll.
    p2_pin_irq_t *reg = ACTIVE_IRQ;
    if ((uintptr_t)reg == generation && mp_sched_schedule(MP_OBJ_FROM_PTR(&deliver_obj), MP_OBJ_FROM_PTR(reg))) {
        p2_irq_pending = 0;
    }
}

static unsigned check_registration(mp_obj_t pin) {
    unsigned number = p2_irq_pin_number(pin);
    if (p2_vm_resetting || pair_owner != ACTIVE_IRQ || (ACTIVE_IRQ && ACTIVE_IRQ->pin != pin)) {
        mp_raise_OSError(MP_EBUSY);
    }
    return number;
}

static mp_obj_t pin_irq(size_t n, const mp_obj_t *args, mp_map_t *kw) {
    enum { ARG_handler, ARG_trigger, ARG_hard };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_handler, MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_trigger, MP_ARG_INT, {.u_int = P2_IRQ_RISING | P2_IRQ_FALLING} },
        { MP_QSTR_hard, MP_ARG_KW_ONLY | MP_ARG_BOOL, {.u_bool = false} },
    };
    mp_arg_val_t vals[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n - 1, args + 1, kw, MP_ARRAY_SIZE(allowed), allowed, vals);
    mp_obj_t pin = args[0];
    mp_obj_t handler = vals[ARG_handler].u_obj;
    mp_int_t trigger = vals[ARG_trigger].u_int;
    if (vals[ARG_hard].u_bool) {
        mp_raise_ValueError(MP_ERROR_TEXT("hard IRQ unsupported"));
    }
    if (trigger < 1 || trigger > (P2_IRQ_RISING | P2_IRQ_FALLING)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid edge trigger"));
    }
    p2_irq_pin_number(pin);
    if (handler == MP_OBJ_NULL) {
        if (n != 1 || kw->used) {
            mp_raise_TypeError(MP_ERROR_TEXT("missing handler"));
        }
        return ACTIVE_IRQ && ACTIVE_IRQ->pin == pin ? MP_OBJ_FROM_PTR(ACTIVE_IRQ) : mp_const_none;
    }
    if (handler == mp_const_none) {
        p2_irq_pin_detach(pin);
        return mp_const_none;
    }
    if (!mp_obj_is_callable(handler)) {
        mp_raise_TypeError(MP_ERROR_TEXT("handler must be callable"));
    }
    check_registration(pin);
    p2_pin_irq_t *reg = mp_obj_malloc(p2_pin_irq_t, &p2_pin_irq_type);
    // GC/finalisers during allocation can close the Pin or claim the slot.
    // All conversions and all allocation precede the final ownership check.
    reg->number = check_registration(pin);
    reg->pin = pin;
    reg->handler = handler;
    reg->trigger = trigger;
    reg->delivered = false;
    uint32_t state = p2_irq_save();
    if (!p2_irq_pair_claim(reg, ACTIVE_IRQ)) {
        p2_irq_restore(state);
        mp_raise_OSError(MP_EBUSY);
    }
    p2_irq_native_install();
    MP_STATE_PORT(p2_active_pin_irq) = reg;
    p2_irq_generation = (uintptr_t)reg;
    p2_irq_pending = 0;
    p2_irq_native_arm(reg->number, reg->trigger);
    p2_irq_restore(state);
    return MP_OBJ_FROM_PTR(reg);
}
MP_DEFINE_CONST_FUN_OBJ_KW(p2_pin_irq_obj, 1, pin_irq);

static mp_obj_t disable_irq(void) {
    return MP_OBJ_NEW_SMALL_INT((mp_int_t)p2_irq_save());
}
MP_DEFINE_CONST_FUN_OBJ_0(p2_disable_irq_obj, disable_irq);

static mp_obj_t enable_irq(mp_obj_t token) {
    if (token != MP_OBJ_NEW_SMALL_INT(0) && token != MP_OBJ_NEW_SMALL_INT(1)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid IRQ token"));
    }
    p2_irq_restore(MP_OBJ_SMALL_INT_VALUE(token));
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_1(p2_enable_irq_obj, enable_irq);
