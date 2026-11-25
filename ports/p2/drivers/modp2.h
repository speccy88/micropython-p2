// SPDX-License-Identifier: MIT
#ifndef MICROPY_INCLUDED_P2_MODP2_H
#define MICROPY_INCLUDED_P2_MODP2_H
#include "py/runtime.h"
#include "py/mperrno.h"
#include "p2resources.h"
extern const mp_obj_type_t p2_pin_type, p2_smartpin_type, p2_psram_type, p2_cog_type;
// At a transfer boundary, Ctrl-C may unwind this native frame. Calling
// arbitrary scheduled Python while a resizable hub buffer is borrowed
// would invalidate the pointer. The single driver VM runs callbacks after
// returning to bytecode. Compute-only threaded builds exclude these drivers.
void p2_poll_borrowed_io(void);
static inline unsigned p2_arg_range(mp_obj_t obj, unsigned max) {
    mp_int_t n = mp_obj_get_int(obj);
    if (n < 0 || (mp_uint_t)n > max) {
        mp_raise_ValueError(MP_ERROR_TEXT("argument out of range"));
    }
    return (unsigned)n;
}
static inline uint32_t p2_arg_word(mp_obj_t obj) {
    if (!mp_obj_is_int(obj)) {
        mp_raise_TypeError(MP_ERROR_TEXT("expected integer"));
    }
    return mp_obj_int_get_uint_checked(obj);
}
#endif
