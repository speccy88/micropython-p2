// SPDX-License-Identifier: MIT
#include "py/mpconfig.h"
#if P2_ENABLE_BUSES
#include "common.h"

typedef struct {
    mp_obj_base_t base;
    uint8_t pins[3];
    uint8_t polarity, phase, lsb;
    uint32_t half_cycles;
    bool active;
} p2_spi_t;
static void configure(mp_obj_base_t *base, size_t n, const mp_obj_t *args, mp_map_t *kw) {
    if (!p2_on_vm_cog()) { mp_raise_OSError(MP_EPERM); }
    p2_spi_t *s = (p2_spi_t *)base;
    enum { BAUD, POL, PHASE, BITS, FIRST, SCK, MOSI, MISO };
    static const mp_arg_t fields[] = {
        { MP_QSTR_baudrate, MP_ARG_INT, {.u_int = 500000} },
        { MP_QSTR_polarity, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_phase, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_bits, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 8} },
        { MP_QSTR_firstbit, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_sck, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1} },
        { MP_QSTR_mosi, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1} },
        { MP_QSTR_miso, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = -1} },
    };
    mp_arg_val_t v[MP_ARRAY_SIZE(fields)];
    mp_arg_parse_all(n, args, kw, MP_ARRAY_SIZE(fields), fields, v);
    int baud = v[BAUD].u_int;
    if (baud < 1000 || baud > 4000000 || v[BITS].u_int != 8 ||
        (unsigned)v[POL].u_int > 1 || (unsigned)v[PHASE].u_int > 1 || (unsigned)v[FIRST].u_int > 1) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid SPI settings"));
    }
    uint8_t pins[3];
    for (size_t i = 0; i < 3; ++i) {
        int num = v[SCK + i].u_int;
        pins[i] = num == -1 && s->active ? s->pins[i] : bus_pin(num);
        if (s->active && pins[i] != s->pins[i]) {
            mp_raise_ValueError(MP_ERROR_TEXT("deinit before moving pins"));
        }
    }
    // Using the same data pad for MOSI/MISO samples the driven pad. Useful for
    // a wire-free loopback test. SCK always needs a separate physical pad.
    if (!s->active) { claim_bus(pins, pins[1] == pins[2] ? 2 : 3, P2_OWNER_SPI); }
    for (unsigned i = 0; i < 3; ++i) { s->pins[i] = pins[i]; }
    s->polarity = v[POL].u_int;
    s->phase = v[PHASE].u_int;
    s->lsb = v[FIRST].u_int;
    s->half_cycles = (P2_CLOCK_HZ / 2 + (unsigned)baud - 1) / (unsigned)baud;
    s->active = true;
    mp_hal_pin_write(pins[0], s->polarity);
    mp_hal_pin_write(pins[1], 0);
    mp_hal_pin_output(pins[0]);
    mp_hal_pin_output(pins[1]);
    if (pins[1] != pins[2]) { mp_hal_pin_input(pins[2]); }
}
static mp_obj_t make(const mp_obj_type_t *type, size_t n, size_t nk, const mp_obj_t *args) {
    p2_spi_t *s = mp_obj_malloc_with_finaliser(p2_spi_t, type);
    s->active = false;
    mp_map_t kw;
    mp_map_init_fixed_table(&kw, nk, args + n);
    configure(&s->base, n, args, &kw);
    return MP_OBJ_FROM_PTR(s);
}
static void close_bus(mp_obj_base_t *base) {
    p2_spi_t *s = (p2_spi_t *)base;
    if (s->active) {
        p2_pins_release(s->pins, s->pins[1] == s->pins[2] ? 2 : 3, P2_OWNER_SPI);
        s->active = false;
    }
}
static mp_obj_t release(mp_obj_t o) { close_bus(MP_OBJ_TO_PTR(o)); return mp_const_none; }
static MP_DEFINE_CONST_FUN_OBJ_1(release_obj, release);
static void attr(mp_obj_t o, qstr a, mp_obj_t *d) { bus_attr(o, a, d, &release_obj); }

static void transfer(mp_obj_base_t *base, size_t n, const uint8_t *src, uint8_t *dest) {
    p2_spi_t *s = (p2_spi_t *)base;
    require_active(s->active);
    for (size_t i = 0; i < n; ++i) {
        uint8_t out = src[i], in = 0;
        for (unsigned bit = 0; bit < 8; ++bit) {
            unsigned shift = s->lsb ? bit : 7 - bit;
            if (s->phase) { mp_hal_pin_write(s->pins[0], !s->polarity); }
            mp_hal_pin_write(s->pins[1], (out >> shift) & 1);
            __asm__ volatile ("waitx %0" :: "r"(s->half_cycles));
            mp_hal_pin_write(s->pins[0], s->phase ? s->polarity : !s->polarity);
            in |= mp_hal_pin_read(s->pins[2]) << shift;
            __asm__ volatile ("waitx %0" :: "r"(s->half_cycles));
            if (!s->phase) { mp_hal_pin_write(s->pins[0], s->polarity); }
        }
        if (dest != NULL) { dest[i] = in; }
        if ((i & 31) == 31) {
            mp_event_handle_nowait();
            require_active(s->active);
        }
    }
}
static const mp_machine_spi_p_t protocol = { .init = configure, .deinit = close_bus, .transfer = transfer };
MP_DEFINE_CONST_OBJ_TYPE(p2_soft_spi_type, MP_QSTR_SoftSPI, MP_TYPE_FLAG_NONE,
    make_new, make, attr, attr, protocol, &protocol, locals_dict, &mp_machine_spi_locals_dict);
#endif
