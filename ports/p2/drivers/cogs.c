// SPDX-License-Identifier: MIT
#include "modp2.h"
extern const uint8_t p2_counter_driver[];
extern int p2_driver_launch(const void *entry, volatile void *mailbox);
typedef struct {
    volatile uint32_t ready, count, interval;
    int cog_plus_one;
} counter_slot_t;
static counter_slot_t drivers[6];
typedef struct {
    mp_obj_base_t base;
    counter_slot_t *slot;
} cog_obj_t;
static void stop_slot(counter_slot_t *slot) {
    if (slot->cog_plus_one) {
        __asm__ volatile ("cogstop %0" :: "r"(slot->cog_plus_one - 1) : "memory");
        slot->cog_plus_one = 0;
    }
}
void p2_cogs_reset(void) {
    for (size_t i = 0; i < MP_ARRAY_SIZE(drivers); ++i) { stop_slot(&drivers[i]); }
}
static mp_obj_t cog_make_new(const mp_obj_type_t *type, size_t n, size_t nk, const mp_obj_t *args) {
    mp_arg_check_num(n, nk, 1, 1, false);
    if (p2_vm_resetting) { mp_raise_OSError(MP_EBUSY); }
    unsigned period_us = p2_arg_range(args[0], 1000000);
    if (!period_us) { mp_raise_ValueError(MP_ERROR_TEXT("period must be positive")); }
    cog_obj_t *self = mp_obj_malloc_with_finaliser(cog_obj_t, type);
    self->slot = NULL;
    counter_slot_t *slot = NULL;
    for (size_t i = 0; i < MP_ARRAY_SIZE(drivers); ++i) {
        if (!drivers[i].cog_plus_one) { slot = &drivers[i]; break; }
    }
    if (!slot) { mp_raise_OSError(MP_EBUSY); }
    slot->ready = slot->count = 0;
    slot->interval = period_us * (P2_CLOCK_HZ / 1000000);
    int id = p2_driver_launch(p2_counter_driver, slot);
    if (id < 0) { mp_raise_OSError(MP_EBUSY); }
    slot->cog_plus_one = id + 1;
    if (id < 2) { stop_slot(slot); mp_raise_OSError(MP_EBUSY); }
    uint32_t start = p2_ct();
    while (!slot->ready) {
        if (p2_ct() - start > P2_CLOCK_HZ / 100) {
            stop_slot(slot);
            mp_raise_OSError(MP_ETIMEDOUT);
        }
    }
    self->slot = slot;
    return MP_OBJ_FROM_PTR(self);
}
static counter_slot_t *get_slot(mp_obj_t o) {
    cog_obj_t *self = MP_OBJ_TO_PTR(o);
    if (!self->slot || !self->slot->cog_plus_one) { mp_raise_OSError(MP_ENODEV); }
    return self->slot;
}
static mp_obj_t stop(mp_obj_t o) {
    cog_obj_t *self = MP_OBJ_TO_PTR(o);
    if (self->slot) { stop_slot(self->slot); self->slot = NULL; }
    return mp_const_none;
}
static mp_obj_t cog_id(mp_obj_t o) { return MP_OBJ_NEW_SMALL_INT(get_slot(o)->cog_plus_one - 1); }
static mp_obj_t cog_count(mp_obj_t o) { return mp_obj_new_int_from_uint(get_slot(o)->count); }
static MP_DEFINE_CONST_FUN_OBJ_1(stop_obj, stop);
static MP_DEFINE_CONST_FUN_OBJ_1(id_obj, cog_id);
static MP_DEFINE_CONST_FUN_OBJ_1(count_obj, cog_count);
static const mp_rom_map_elem_t cog_locals[] = {
    {MP_ROM_QSTR(MP_QSTR_id), MP_ROM_PTR(&id_obj)},
    {MP_ROM_QSTR(MP_QSTR_count), MP_ROM_PTR(&count_obj)},
    {MP_ROM_QSTR(MP_QSTR_stop), MP_ROM_PTR(&stop_obj)},
    {MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&stop_obj)},
};
static MP_DEFINE_CONST_DICT(cog_dict, cog_locals);
MP_DEFINE_CONST_OBJ_TYPE(p2_cog_type, MP_QSTR_Cog, MP_TYPE_FLAG_NONE, make_new, cog_make_new, locals_dict, &cog_dict);
