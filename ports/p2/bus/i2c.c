// SPDX-License-Identifier: MIT
#include "py/mpconfig.h"
#if P2_ENABLE_BUSES
#include "common.h"

typedef struct {
    mp_machine_soft_i2c_obj_t hw;
    uint8_t pins[2];
    bool active;
} p2_i2c_t;

static const mp_machine_i2c_p_t *soft(void) {
    return MP_OBJ_TYPE_GET_SLOT(&mp_machine_soft_i2c_type, protocol);
}
static void configure(mp_obj_base_t *base, size_t n, const mp_obj_t *args, mp_map_t *kw) {
    if (!p2_on_vm_cog()) {
        mp_raise_OSError(MP_EPERM);
    }
    p2_i2c_t *s = (p2_i2c_t *)base;
    enum { SCL, SDA, FREQ, TIMEOUT };
    static const mp_arg_t fields[] = {
        { MP_QSTR_scl, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1} },
        { MP_QSTR_sda, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1} },
        { MP_QSTR_freq, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 400000} },
        { MP_QSTR_timeout, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 50000} },
    };
    mp_arg_val_t v[MP_ARRAY_SIZE(fields)];
    mp_arg_parse_all(n, args, kw, MP_ARRAY_SIZE(fields), fields, v);
    uint8_t pins[] = {
        v[SCL].u_int == -1 && s->active ? s->pins[0] : bus_pin(v[SCL].u_int),
        v[SDA].u_int == -1 && s->active ? s->pins[1] : bus_pin(v[SDA].u_int),
    };
    int hz = v[FREQ].u_int, timeout = v[TIMEOUT].u_int;
    if (hz < 1000 || hz > 500000 || timeout < 1 || timeout > 1000000) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid I2C timing"));
    }
    if (s->active && (s->pins[0] != pins[0] || s->pins[1] != pins[1])) {
        mp_raise_ValueError(MP_ERROR_TEXT("deinit before moving pins"));
    }
    if (!s->active) {
        claim_bus(pins, 2, P2_OWNER_I2C);
    }
    s->hw.scl = s->pins[0] = pins[0];
    s->hw.sda = s->pins[1] = pins[1];
    s->active = true;
    s->hw.us_delay = (500000u + (unsigned)hz - 1) / (unsigned)hz;
    s->hw.us_timeout = timeout;
    mp_hal_pin_open_drain(s->hw.scl);
    mp_hal_pin_open_drain(s->hw.sda);
}
static mp_obj_t make(const mp_obj_type_t *type, size_t n, size_t nk, const mp_obj_t *args) {
    p2_i2c_t *s = mp_obj_malloc_with_finaliser(p2_i2c_t, type);
    s->active = false;
    mp_map_t kw;
    mp_map_init_fixed_table(&kw, nk, args + n);
    configure(&s->hw.base, n, args, &kw);
    return MP_OBJ_FROM_PTR(s);
}
static void close_bus(mp_obj_base_t *base) {
    p2_i2c_t *s = (p2_i2c_t *)base;
    if (s->active) {
        p2_pins_release(s->pins, 2, P2_OWNER_I2C);
        s->active = false;
    }
}
static mp_obj_t release(mp_obj_t o) {
    close_bus(MP_OBJ_TO_PTR(o));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(release_obj, release);
static void attr(mp_obj_t o, qstr a, mp_obj_t *d) {
    bus_attr(o, a, d, &release_obj);
}

static int checked(p2_i2c_t *s, int status) {
    if (status < 0) {
        // A target may still hold SCL. Release both local open-drain drivers.
        mp_hal_pin_od_high(s->hw.scl);
        mp_hal_pin_od_high(s->hw.sda);
    }
    return status;
}
static int start(mp_obj_base_t *o) {
    p2_i2c_t *s = (p2_i2c_t *)o;
    require_active(s->active);
    return checked(s, soft()->start(o));
}
static int stop(mp_obj_base_t *o) {
    p2_i2c_t *s = (p2_i2c_t *)o;
    require_active(s->active);
    return checked(s, soft()->stop(o));
}
static int read_bytes(mp_obj_base_t *o, uint8_t *dst, size_t n, bool nack) {
    p2_i2c_t *s = (p2_i2c_t *)o;
    require_active(s->active);
    return checked(s, soft()->read(o, dst, n, nack));
}
static int write_bytes(mp_obj_base_t *o, const uint8_t *src, size_t n) {
    p2_i2c_t *s = (p2_i2c_t *)o;
    require_active(s->active);
    return checked(s, soft()->write(o, src, n));
}
static int transfer(mp_obj_base_t *o, uint16_t addr, size_t n, mp_machine_i2c_buf_t *bufs, unsigned flags) {
    p2_i2c_t *s = (p2_i2c_t *)o;
    require_active(s->active);
    if (addr > 127) {
        return -MP_EINVAL;
    }
    return checked(s, soft()->transfer(o, addr, n, bufs, flags));
}
static const mp_machine_i2c_p_t protocol = {
    .init = configure, .deinit = close_bus, .start = start, .stop = stop,
    .read = read_bytes, .write = write_bytes, .transfer = transfer,
};
MP_DEFINE_CONST_OBJ_TYPE(p2_soft_i2c_type, MP_QSTR_SoftI2C, MP_TYPE_FLAG_NONE,
    make_new, make, attr, attr, protocol, &protocol, locals_dict, &mp_machine_i2c_locals_dict);
#endif
