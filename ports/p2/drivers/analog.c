// SPDX-License-Identifier: MIT
#include "modp2.h"
// Integer pin IDs give each instance exclusive ownership until deinit.
typedef struct {
    mp_obj_base_t base;
    uint8_t pin;
    bool active;
    uint32_t period, frame, duty;
    uint32_t gnd, vdd;
} channel_t;
static channel_t *channel_new(const mp_obj_type_t *type, unsigned pin) {
    channel_t *c = mp_obj_malloc_with_finaliser(channel_t, type);
    c->pin = pin;
    c->active = false;
    int error = p2_pins_claim(&c->pin, 1, P2_OWNER_SMARTPIN);
    if (error) { mp_raise_OSError(error == -2 ? MP_EBUSY : MP_EPERM); }
    c->active = true;
    return c;
}
static channel_t *channel(mp_obj_t o) {
    if (!p2_on_vm_cog()) { mp_raise_OSError(MP_EPERM); }
    channel_t *c = MP_OBJ_TO_PTR(o);
    if (!c->active) { mp_raise_OSError(MP_ENODEV); }
    return c;
}
static mp_obj_t deinit(mp_obj_t o) {
    channel_t *c = MP_OBJ_TO_PTR(o);
    if (c->active) { p2_pins_release(&c->pin, 1, P2_OWNER_SMARTPIN); c->active = false; }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(deinit_obj, deinit);
static void config(unsigned pin, uint32_t mode, uint32_t x, uint32_t y) {
    __asm__ volatile ("dirl %0\n\twrpin %1,%0\n\twxpin %2,%0\n\twypin %3,%0\n\tdirh %0"
        :: "r"(pin), "r"(mode), "r"(x), "r"(y) : "memory");
}
static void write_y(unsigned pin, uint32_t y) {
    __asm__ volatile ("wypin %0,%1" :: "r"(y), "r"(pin) : "memory");
}
static unsigned pwm_value(channel_t *c) { return (c->frame * c->duty + 32767u) / 65535u; }
static void pwm_config(channel_t *c, uint32_t hz) {
    uint32_t cycles = (P2_CLOCK_HZ + hz / 2) / hz;
    uint32_t base = (cycles + 65534u) / 65535u;
    c->frame = (cycles + base / 2) / base;
    c->period = base * c->frame;
    config(c->pin, 0x12 | 0x40, (c->frame << 16) | base, pwm_value(c));
}
static mp_obj_t pwm_new(const mp_obj_type_t *type, size_t n, size_t nk, const mp_obj_t *args) {
    enum { PIN, HZ, DUTY };
    static const mp_arg_t allowed[] = {
        {MP_QSTR_pin, MP_ARG_INT | MP_ARG_REQUIRED, {.u_int = 0}},
        {MP_QSTR_freq, MP_ARG_INT | MP_ARG_KW_ONLY, {.u_int = 1000}},
        {MP_QSTR_duty_u16, MP_ARG_INT | MP_ARG_KW_ONLY, {.u_int = 0}},
    };
    mp_arg_val_t vals[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all_kw_array(n, nk, args, MP_ARRAY_SIZE(allowed), allowed, vals);
    int pin = vals[PIN].u_int, hz = vals[HZ].u_int, duty = vals[DUTY].u_int;
    if ((unsigned)pin > 63 || hz < 1 || hz > (int)(P2_CLOCK_HZ / 2) || (unsigned)duty > 65535u) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid PWM configuration"));
    }
    channel_t *c = channel_new(type, pin);
    c->duty = duty;
    pwm_config(c, hz);
    return MP_OBJ_FROM_PTR(c);
}
static mp_obj_t pwm_freq(size_t n, const mp_obj_t *args) {
    if (n == 1) { return mp_obj_new_int_from_uint(P2_CLOCK_HZ / channel(args[0])->period); }
    unsigned hz = p2_arg_range(args[1], P2_CLOCK_HZ / 2);
    if (!hz) { mp_raise_ValueError(MP_ERROR_TEXT("positive frequency required")); }
    pwm_config(channel(args[0]), hz);
    return mp_const_none;
}
static mp_obj_t pwm_duty(size_t n, const mp_obj_t *args) {
    if (n == 1) { return MP_OBJ_NEW_SMALL_INT(channel(args[0])->duty); }
    unsigned duty = p2_arg_range(args[1], 65535);
    channel_t *c = channel(args[0]);
    c->duty = duty;
    write_y(c->pin, pwm_value(c));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(freq_obj, 1, 2, pwm_freq);
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(duty_obj, 1, 2, pwm_duty);
static const mp_rom_map_elem_t pwm_locals[] = {
    {MP_ROM_QSTR(MP_QSTR_freq), MP_ROM_PTR(&freq_obj)},
    {MP_ROM_QSTR(MP_QSTR_duty_u16), MP_ROM_PTR(&duty_obj)},
    {MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&deinit_obj)},
    {MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&deinit_obj)},
};
static MP_DEFINE_CONST_DICT(pwm_dict, pwm_locals);
MP_DEFINE_CONST_OBJ_TYPE(p2_pwm_type, MP_QSTR_PWM, MP_TYPE_FLAG_NONE, make_new, pwm_new, locals_dict, &pwm_dict);

static bool adc_get(unsigned pin, uint32_t *value) {
    uint32_t start = p2_ct(), ready;
    do {
        __asm__ volatile ("testp %1 wc\n\twrc %0" : "=r"(ready) : "r"(pin));
        if (ready) {
            __asm__ volatile ("rdpin %0,%1" : "=r"(*value) : "r"(pin) : "memory");
            return true;
        }
    } while (p2_ct() - start < P2_CLOCK_HZ / 100);
    return false;
}
static bool adc_source(unsigned pin, uint32_t source, uint32_t *value) {
    config(pin, source | 0x30, 11, 0);
    // Discard startup conversions; SINC2 uses two successive periods.
    for (unsigned i = 0; i < 4; ++i) { if (!adc_get(pin, value)) { return false; } }
    return true;
}
static mp_obj_t adc_new(const mp_obj_type_t *type, size_t n, size_t nk, const mp_obj_t *args) {
    mp_arg_check_num(n, nk, 1, 1, false);
    channel_t *c = channel_new(type, p2_arg_range(args[0], 63));
    uint32_t ignore;
    if (!adc_source(c->pin, 0x100000, &c->gnd) || !adc_source(c->pin, 0x108000, &c->vdd)
        || !adc_source(c->pin, 0x118000, &ignore) || c->vdd <= c->gnd) {
        deinit(MP_OBJ_FROM_PTR(c));
        mp_raise_OSError(MP_EIO);
    }
    return MP_OBJ_FROM_PTR(c);
}
static mp_obj_t adc_read(mp_obj_t o) {
    channel_t *c = channel(o);
    uint32_t raw;
    if (!adc_get(c->pin, &raw)) { mp_raise_OSError(MP_ETIMEDOUT); }
    if (raw <= c->gnd) { return MP_OBJ_NEW_SMALL_INT(0); }
    if (raw >= c->vdd) { return MP_OBJ_NEW_SMALL_INT(65535); }
    uint32_t span = c->vdd - c->gnd;
    return MP_OBJ_NEW_SMALL_INT(((raw - c->gnd) * 65535u + span / 2) / span);
}
static MP_DEFINE_CONST_FUN_OBJ_1(adc_read_obj, adc_read);
static const mp_rom_map_elem_t adc_locals[] = {
    {MP_ROM_QSTR(MP_QSTR_read_u16), MP_ROM_PTR(&adc_read_obj)},
    {MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&deinit_obj)},
    {MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&deinit_obj)},
};
static MP_DEFINE_CONST_DICT(adc_dict, adc_locals);
MP_DEFINE_CONST_OBJ_TYPE(p2_adc_type, MP_QSTR_ADC, MP_TYPE_FLAG_NONE, make_new, adc_new, locals_dict, &adc_dict);
static mp_obj_t dac_new(const mp_obj_type_t *type, size_t n, size_t nk, const mp_obj_t *args) {
    mp_arg_check_num(n, nk, 1, 1, false);
    channel_t *c = channel_new(type, p2_arg_range(args[0], 63));
    config(c->pin, 0x140000 | 0x40 | 0x06, 256, 0);
    return MP_OBJ_FROM_PTR(c);
}
static mp_obj_t dac_write(mp_obj_t o, mp_obj_t value) {
    unsigned duty = p2_arg_range(value, 65535);
    write_y(channel(o)->pin, duty);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(dac_write_obj, dac_write);
static const mp_rom_map_elem_t dac_locals[] = {
    {MP_ROM_QSTR(MP_QSTR_write_u16), MP_ROM_PTR(&dac_write_obj)},
    {MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&deinit_obj)},
    {MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&deinit_obj)},
};
static MP_DEFINE_CONST_DICT(dac_dict, dac_locals);
MP_DEFINE_CONST_OBJ_TYPE(p2_dac_type, MP_QSTR_DAC, MP_TYPE_FLAG_NONE, make_new, dac_new, locals_dict, &dac_dict);
