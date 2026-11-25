// SPDX-License-Identifier: MIT
// Managed HUBEXEC binary ABI. The hardware cog only sees its private hub mailbox.
#include <string.h>
#include "modp2.h"
#include "py/objstr.h"

#define HEADER_BYTES 24
#define MAX_CODE 4096
#define MAX_WORDS 256
#define MAX_PINS 8
#define APP_COGS 6
extern int p2_driver_launch(const void *entry, volatile void *mailbox);
MP_REGISTER_ROOT_POINTER(void *p2_active_drivers[6]);

typedef struct {
    mp_obj_base_t base;
    uint16_t code_words, mailbox_words;
    uint8_t pins[MAX_PINS], pin_count;
    int8_t cog;
    uint32_t storage[];
} driver_t;

static uint32_t le32(const uint8_t *p) {
    return p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static uint32_t fnv(uint32_t hash, const uint8_t *p, size_t size) {
    for (size_t i = 0; i < size; ++i) { hash = (hash ^ p[i]) * 16777619u;
    }
    return hash;
}

static void stop_driver(driver_t *self) {
    if (self->cog < 0) {
        return;
    }
    __asm__ volatile ("cogstop %0" : : "r" ((unsigned)self->cog) : "memory");
    p2_pins_release(self->pins, self->pin_count, P2_OWNER_DRIVER);
    MP_STATE_PORT(p2_active_drivers)[self->cog - 2] = NULL;
    self->cog = -1;
}

void p2_hubdrivers_reset(void) {
    for (size_t i = 0; i < APP_COGS; ++i) {
        driver_t *self = MP_STATE_PORT(p2_active_drivers)[i];
        if (self) {
            stop_driver(self);
        }
    }
}

static mp_obj_t make_driver(const mp_obj_type_t *type, size_t n, size_t nk, const mp_obj_t *args) {
    #if P2_PROFILE_THREADED
    if (!p2_on_vm_cog()) {
        mp_raise_OSError(MP_EPERM);
    }
    #endif
    enum { ARG_image, ARG_pins };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_image, MP_ARG_OBJ | MP_ARG_REQUIRED, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_pins, MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
    };
    mp_arg_val_t values[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all_kw_array(n, nk, args, MP_ARRAY_SIZE(allowed), allowed, values);
    mp_obj_t image = values[ARG_image].u_obj;
    if (p2_vm_resetting) {
        mp_raise_OSError(MP_EBUSY);
    }
    if (!mp_obj_is_type(image, &mp_type_bytes)) {
        mp_raise_TypeError(MP_ERROR_TEXT("driver image requires bytes"));
    }
    size_t size;
    const uint8_t *src = (const uint8_t *)mp_obj_str_get_data(image, &size);
    if (size < HEADER_BYTES || memcmp(src, "P2D1\x01\x00\x18\x00", 8)) {
        mp_raise_ValueError(MP_ERROR_TEXT("driver header"));
    }
    uint32_t code = le32(src + 8), entry = le32(src + 12), words = le32(src + 16);
    if (!code || code > MAX_CODE || code % 4 || size - HEADER_BYTES != code
        || entry % 4 || entry >= code || words < 4 || words > MAX_WORDS
        || fnv(fnv(2166136261u, src, 20), src + HEADER_BYTES, code) != le32(src + 20)) {
        mp_raise_ValueError(MP_ERROR_TEXT("driver image"));
    }
    size_t pin_count = 0;
    uint8_t pins[MAX_PINS];
    if (values[ARG_pins].u_obj != MP_OBJ_NULL) {
        mp_obj_t *items, snapshot[MAX_PINS];
        mp_obj_get_array(values[ARG_pins].u_obj, &pin_count, &items);
        if (pin_count > MAX_PINS) {
            mp_raise_ValueError(MP_ERROR_TEXT("too many driver pins"));
        }
        if (pin_count) {
            memcpy(snapshot, items, pin_count * sizeof(mp_obj_t));
        }
        for (size_t i = 0; i < pin_count; ++i) { pins[i] = p2_arg_range(snapshot[i], 63);
        }
    }
    driver_t *self = mp_obj_malloc_var(driver_t, storage, uint32_t, code / 4 + words, type);
    self->code_words = code / 4;
    self->mailbox_words = words;
    self->pin_count = pin_count;
    self->cog = -1;
    memcpy(self->pins, pins, pin_count);
    memcpy(self->storage, src + HEADER_BYTES, code);
    uint32_t *mailbox = self->storage + self->code_words;
    memset(mailbox, 0, 4 * words);
    int result = p2_pins_claim(self->pins, pin_count, P2_OWNER_DRIVER);
    if (result) {
        mp_raise_OSError(result == -2 ? MP_EBUSY : MP_EPERM);
    }
    int cog = p2_driver_launch(self->storage + entry / 4, mailbox);
    if (cog < 2 || cog >= 8) {
        if (cog >= 0 && cog < 8) {
            __asm__ volatile ("cogstop %0" : : "r" (cog) : "memory");
        }
        p2_pins_release(self->pins, pin_count, P2_OWNER_DRIVER);
        mp_raise_OSError(MP_EBUSY);
    }
    self->cog = cog;
    MP_STATE_PORT(p2_active_drivers)[cog - 2] = self;
    uint32_t start = p2_ct();
    while (*(volatile uint32_t *)mailbox != 1) {
        if (p2_ct() - start > P2_CLOCK_HZ / 100) {
            stop_driver(self);
            mp_raise_OSError(MP_ETIMEDOUT);
        }
    }
    return MP_OBJ_FROM_PTR(self);
}

static driver_t *active(mp_obj_t obj) {
    driver_t *self = MP_OBJ_TO_PTR(obj);
    if (self->cog < 0) {
        mp_raise_OSError(MP_ENODEV);
    }
    return self;
}
static mp_obj_t get_driver(mp_obj_t id) {
    unsigned cog = p2_arg_range(id, 7);
    driver_t *self = cog < 2 ? NULL : MP_STATE_PORT(p2_active_drivers)[cog - 2];
    if (!self) {
        mp_raise_OSError(MP_ENODEV);
    }
    return MP_OBJ_FROM_PTR(self);
}
MP_DEFINE_CONST_FUN_OBJ_1(p2_get_driver_obj, get_driver);

static mp_obj_t driver_id(mp_obj_t obj) {
    return MP_OBJ_NEW_SMALL_INT(active(obj)->cog);
}
static MP_DEFINE_CONST_FUN_OBJ_1(id_obj, driver_id);
static mp_obj_t driver_stop(mp_obj_t obj) {
    #if P2_PROFILE_THREADED
    if (!p2_on_vm_cog()) {
        mp_raise_OSError(MP_EPERM);
    }
    #endif
    stop_driver(MP_OBJ_TO_PTR(obj));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(stop_obj, driver_stop);

static mp_obj_t word(size_t n, const mp_obj_t *args) {
    unsigned index = p2_arg_range(args[1], MAX_WORDS - 1);
    uint32_t value = n == 3 ? p2_arg_word(args[2]) : 0;
    driver_t *self = active(args[0]);
    if (index >= self->mailbox_words || (n == 3 && index < 4 && index != 1)) {
        mp_raise_ValueError(MP_ERROR_TEXT("mailbox word"));
    }
    volatile uint32_t *mailbox = self->storage + self->code_words;
    if (n == 3) {
        mailbox[index] = value;
        return mp_const_none;
    }
    return mp_obj_new_int_from_uint(mailbox[index]);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(word_obj, 2, 3, word);

static mp_obj_t transfer(mp_obj_t obj, mp_obj_t first, mp_obj_t buffer, bool write) {
    unsigned index = p2_arg_range(first, MAX_WORDS);
    mp_buffer_info_t buf;
    mp_get_buffer_raise(buffer, &buf, write ? MP_BUFFER_READ : MP_BUFFER_WRITE);
    driver_t *self = active(obj);
    if (index > self->mailbox_words || buf.len % 4 || buf.len / 4 > self->mailbox_words - index
        || (write && index < 4)) {
        mp_raise_ValueError(MP_ERROR_TEXT("mailbox transfer"));
    }
    volatile uint32_t *mailbox = self->storage + self->code_words + index;
    uint8_t *data = buf.buf;
    for (size_t i = 0; i < buf.len / 4; ++i) {
        uint32_t v;
        if (write) {
            __builtin_memcpy(&v, data + 4 * i, 4);
            mailbox[i] = v;
        } else {
            v = mailbox[i];
            __builtin_memcpy(data + 4 * i, &v, 4);
        }
    }
    return MP_OBJ_NEW_SMALL_INT(buf.len);
}
static mp_obj_t driver_write(mp_obj_t obj, mp_obj_t first, mp_obj_t buf) {
    return transfer(obj, first, buf, true);
}
static mp_obj_t driver_readinto(mp_obj_t obj, mp_obj_t first, mp_obj_t buf) {
    return transfer(obj, first, buf, false);
}
static MP_DEFINE_CONST_FUN_OBJ_3(write_obj, driver_write);
static MP_DEFINE_CONST_FUN_OBJ_3(readinto_obj, driver_readinto);
static const mp_rom_map_elem_t driver_locals[] = {
    {MP_ROM_QSTR(MP_QSTR_id), MP_ROM_PTR(&id_obj)}, {MP_ROM_QSTR(MP_QSTR_stop), MP_ROM_PTR(&stop_obj)},
    {MP_ROM_QSTR(MP_QSTR_word), MP_ROM_PTR(&word_obj)}, {MP_ROM_QSTR(MP_QSTR_write), MP_ROM_PTR(&write_obj)},
    {MP_ROM_QSTR(MP_QSTR_readinto), MP_ROM_PTR(&readinto_obj)},
};
static MP_DEFINE_CONST_DICT(driver_dict, driver_locals);
MP_DEFINE_CONST_OBJ_TYPE(p2_driver_type, MP_QSTR_Driver, MP_TYPE_FLAG_NONE, make_new, make_driver, locals_dict, &driver_dict);
