// SPDX-License-Identifier: MIT
#include "py/runtime.h"
#include "py/mphal.h"
#include "py/mperrno.h"
#include "shared/runtime/softtimer.h"
#include "drivers/p2resources.h"

#define TIMER_MAX_MS (0x3fffffffU)
#define TIMER_CYCLES_PER_MS (P2_CLOCK_HZ / 1000U)

typedef struct {
    soft_timer_entry_t entry;
    mp_obj_t callback;
    uint32_t period_ms;
    bool periodic, queued, deliver;
} p2_timer_t;

extern uint64_t p2_cycle_count(void);
static bool timer_armed;
static uint64_t timer_deadline;

uint32_t soft_timer_get_ms(void) {
    return mp_hal_ticks_ms();
}

void soft_timer_schedule_at_ms(uint32_t ticks_ms) {
    uint64_t cycles = p2_cycle_count();
    uint64_t now_ms = cycles / TIMER_CYCLES_PER_MS;
    int32_t delay = soft_timer_ticks_diff(ticks_ms, (uint32_t)now_ms);
    timer_deadline = delay <= 0 ? cycles : (now_ms + (uint32_t)delay) * TIMER_CYCLES_PER_MS;
    timer_armed = true;
}

void p2_timer_poll(void) {
    if (timer_armed && !p2_vm_resetting && p2_cycle_count() >= timer_deadline) {
        timer_armed = false;
        soft_timer_handler();
    }
}

void p2_timer_reset(void) {
    timer_armed = false;
    soft_timer_deinit();
}

static mp_obj_t timer_dispatch(mp_obj_t self_in) {
    p2_timer_t *self = MP_OBJ_TO_PTR(self_in);
    self->queued = false;
    if (self->deliver) {
        self->deliver = false;
        mp_call_function_1(self->callback, self_in);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(timer_dispatch_obj, timer_dispatch);

static void timer_due(soft_timer_entry_t *entry) {
    p2_timer_t *self = (p2_timer_t *)entry;
    if (!self->queued) {
        self->queued = mp_sched_schedule(MP_OBJ_FROM_PTR(&timer_dispatch_obj), MP_OBJ_FROM_PTR(self));
    }
    self->deliver = self->queued;
    if (!self->queued || self->periodic) {
        // Retry if the VM queue filled. Coalesce missed periodic ticks and
        // keep the normal cadence relative to the previous deadline.
        uint32_t now = soft_timer_get_ms();
        entry->mode = SOFT_TIMER_MODE_PERIODIC;
        entry->delta_ms = self->queued ? self->period_ms : 1;
        entry->expiry_ms = now - (now - entry->expiry_ms) % entry->delta_ms;
    } else {
        entry->mode = SOFT_TIMER_MODE_ONE_SHOT;
    }
}

static void timer_init_helper(p2_timer_t *self, size_t n_args, const mp_obj_t *args, mp_map_t *kwargs) {
    enum { ARG_mode, ARG_period, ARG_tick_hz, ARG_callback, ARG_freq, ARG_hard };
    static const mp_arg_t allowed[] = {
        {MP_QSTR_mode, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = SOFT_TIMER_MODE_PERIODIC}},
        {MP_QSTR_period, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL}},
        {MP_QSTR_tick_hz, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 1000}},
        {MP_QSTR_callback, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL}},
        {MP_QSTR_freq, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_rom_obj = MP_ROM_NONE}},
        {MP_QSTR_hard, MP_ARG_KW_ONLY | MP_ARG_BOOL, {.u_bool = false}},
    };
    mp_arg_val_t v[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, args, kwargs, MP_ARRAY_SIZE(allowed), allowed, v);
    if (p2_vm_resetting) {
        mp_raise_OSError(MP_EBUSY);
    }
    mp_int_t mode = v[ARG_mode].u_int;
    if ((mode != SOFT_TIMER_MODE_ONE_SHOT && mode != SOFT_TIMER_MODE_PERIODIC) || v[ARG_hard].u_bool) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid timer mode"));
    }
    mp_obj_t callback = v[ARG_callback].u_obj == MP_OBJ_NULL ? self->callback : v[ARG_callback].u_obj;
    if (callback != mp_const_none && !mp_obj_is_callable(callback)) {
        mp_raise_TypeError(MP_ERROR_TEXT("expected callback"));
    }
    uint64_t period = self->period_ms;
    if (v[ARG_freq].u_obj != mp_const_none) {
        #if MICROPY_PY_BUILTINS_FLOAT
        mp_float_t hz = mp_obj_get_float(v[ARG_freq].u_obj);
        if (!(hz > MICROPY_FLOAT_CONST(1000.0) / (TIMER_MAX_MS + 1U) && hz <= 1000)) {
            mp_raise_ValueError(MP_ERROR_TEXT("frequency out of range"));
        }
        period = (uint32_t)(MICROPY_FLOAT_CONST(1000.0) / hz);
        #else
        mp_int_t hz = mp_obj_get_int(v[ARG_freq].u_obj);
        if (hz <= 0 || hz > 1000) {
            mp_raise_ValueError(MP_ERROR_TEXT("frequency out of range"));
        }
        period = 1000 / hz;
        #endif
    } else if (v[ARG_period].u_obj != MP_OBJ_NULL) {
        mp_int_t ticks = mp_obj_get_int(v[ARG_period].u_obj);
        if (ticks <= 0 || v[ARG_tick_hz].u_int <= 0) {
            mp_raise_ValueError(MP_ERROR_TEXT("period and tick_hz must be positive"));
        }
        period = (uint64_t)ticks * 1000 / (mp_uint_t)v[ARG_tick_hz].u_int;
        if (period == 0) {
            period = 1;
        }
    }
    if (period > TIMER_MAX_MS) {
        mp_raise_ValueError(MP_ERROR_TEXT("period too large"));
    }
    // A failed init leaves the existing timer and its callback intact.
    soft_timer_remove(&self->entry);
    self->deliver = false;
    self->callback = callback;
    self->period_ms = period;
    self->periodic = mode == SOFT_TIMER_MODE_PERIODIC;
    if (callback != mp_const_none) {
        soft_timer_insert(&self->entry, self->period_ms);
    }
}

static mp_obj_t timer_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args) {
    mp_arg_check_num(n_args, n_kw, 0, 1, true);
    if (n_args && mp_obj_get_int(args[0]) != -1) {
        mp_raise_ValueError(MP_ERROR_TEXT("only virtual timers supported"));
    }
    p2_timer_t *self = m_new_obj(p2_timer_t);
    self->entry.pairheap.base.type = type;
    soft_timer_static_init(&self->entry, SOFT_TIMER_MODE_ONE_SHOT, 0, timer_due);
    self->entry.flags = SOFT_TIMER_FLAG_GC_ALLOCATED;
    self->callback = mp_const_none;
    self->period_ms = 1000;
    self->periodic = true;
    self->queued = self->deliver = false;
    if (n_kw) {
        mp_map_t kwargs;
        mp_map_init_fixed_table(&kwargs, n_kw, args + n_args);
        timer_init_helper(self, 0, NULL, &kwargs);
    }
    return MP_OBJ_FROM_PTR(self);
}

static mp_obj_t timer_init(size_t n_args, const mp_obj_t *args, mp_map_t *kwargs) {
    timer_init_helper(MP_OBJ_TO_PTR(args[0]), n_args - 1, args + 1, kwargs);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(timer_init_obj, 1, timer_init);

static mp_obj_t timer_deinit(mp_obj_t self_in) {
    p2_timer_t *self = MP_OBJ_TO_PTR(self_in);
    soft_timer_remove(&self->entry);
    self->deliver = false;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(timer_deinit_obj, timer_deinit);

static const mp_rom_map_elem_t timer_locals[] = {
    {MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&timer_init_obj)},
    {MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&timer_deinit_obj)},
    {MP_ROM_QSTR(MP_QSTR_ONE_SHOT), MP_ROM_INT(SOFT_TIMER_MODE_ONE_SHOT)},
    {MP_ROM_QSTR(MP_QSTR_PERIODIC), MP_ROM_INT(SOFT_TIMER_MODE_PERIODIC)},
};
static MP_DEFINE_CONST_DICT(timer_dict, timer_locals);
MP_DEFINE_CONST_OBJ_TYPE(p2_timer_type, MP_QSTR_Timer, MP_TYPE_FLAG_NONE,
    make_new, timer_new, locals_dict, &timer_dict);
