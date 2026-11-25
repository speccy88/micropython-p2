// SPDX-License-Identifier: MIT
#include "modp2.h"
#if P2_ENABLE_HW_IRQ
#include "irq.h"
#endif

// Ownership belongs to one live Python handle. The pin registry contains only
// small integer tags; native drivers cannot retain pointers to these handles.
enum { PIN_IN, PIN_OUT, PIN_OPEN_DRAIN };
enum { PULL_UP = 1, PULL_DOWN };
typedef struct {
    mp_obj_base_t base;
    uint8_t pin, owner, mode;
} pin_obj_t;

static pin_obj_t *open_pin(mp_obj_t o) {
    if (!p2_on_vm_cog()) {
        mp_raise_OSError(MP_EPERM);
    }
    pin_obj_t *p = MP_OBJ_TO_PTR(o);
    if (!p->owner) {
        mp_raise_OSError(MP_ENODEV);
    }
    return p;
}
#if P2_ENABLE_HW_IRQ
unsigned p2_irq_pin_number(mp_obj_t self) {
    if (!mp_obj_is_type(self, &p2_pin_type)) {
        mp_raise_TypeError(MP_ERROR_TEXT("ordinary Pin required"));
    }
    pin_obj_t *p = open_pin(self);
    if (p->mode != PIN_IN) {
        mp_raise_ValueError(MP_ERROR_TEXT("IRQ requires Pin.IN"));
    }
    return p->pin;
}
#endif
static pin_obj_t *claim_pin(const mp_obj_type_t *type, unsigned pin, unsigned owner) {
    pin_obj_t *p = mp_obj_malloc_with_finaliser(pin_obj_t, type);
    p->pin = pin;
    p->owner = 0;
    int error = p2_pins_claim(&p->pin, 1, owner);
    if (error) {
        mp_raise_OSError(error == -2 ? MP_EBUSY : MP_EPERM);
    }
    p->owner = owner;
    return p;
}
static mp_obj_t release_pin(mp_obj_t self) {
    pin_obj_t *p = MP_OBJ_TO_PTR(self);
    if (p->owner) {
        #if P2_ENABLE_HW_IRQ
        p2_irq_pin_detach(self);
        #endif
        p2_pins_release(&p->pin, 1, p->owner);
        p->owner = 0;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(release_pin_obj, release_pin);
static uint32_t sample(unsigned pin) {
    uint32_t bit;
    __asm__ volatile ("testp %1 wc\n\twrc %0" : "=r" (bit) : "r" (pin));
    return bit;
}
static void write_latch(unsigned pin, bool high) {
    if (high) {
        __asm__ volatile ("outh %0" : : "r" (pin) : "memory");
    } else {
        __asm__ volatile ("outl %0" : : "r" (pin) : "memory");
    }
}
static void configure_pin(pin_obj_t *p, int mode, unsigned pull, bool high) {
    unsigned pin = p->pin, config = 0;
    p2_pin_float(pin);
    p->mode = mode;
    if (mode == PIN_OPEN_DRAIN) {
        config = 0x3800;
    }                                                // high drive floats
    if (pull == PULL_UP) {
        config = 0x1000;
        high = true;
    }
    if (pull == PULL_DOWN) {
        config = 0x0200;
        high = false;
    }
    __asm__ volatile ("wrpin %0, %1" : : "r" (config), "r" (pin) : "memory");
    write_latch(pin, high);
    if (mode != PIN_IN || pull) {
        __asm__ volatile ("dirh %0" : : "r" (pin) : "memory");
    }
}
static mp_obj_t pin_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args) {
    enum { ARG_id, ARG_mode, ARG_pull, ARG_value };
    static const mp_arg_t allowed[] = {
        {MP_QSTR_id, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0}},
        {MP_QSTR_mode, MP_ARG_INT, {.u_int = PIN_IN}},
        {MP_QSTR_pull, MP_ARG_OBJ, {.u_obj = mp_const_none}},
        {MP_QSTR_value, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL}},
    };
    mp_arg_val_t vals[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all_kw_array(n_args, n_kw, args, MP_ARRAY_SIZE(allowed), allowed, vals);
    int id = vals[ARG_id].u_int, mode = vals[ARG_mode].u_int;
    int pull = vals[ARG_pull].u_obj == mp_const_none ? 0 : mp_obj_get_int(vals[ARG_pull].u_obj);
    if (id < 0 || id >= 64 || mode < PIN_IN || mode > PIN_OPEN_DRAIN || pull < 0 || pull > 2 || (pull && mode != PIN_IN)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid pin, mode or pull"));
    }
    bool value = vals[ARG_value].u_obj == MP_OBJ_NULL ? mode == PIN_OPEN_DRAIN : mp_obj_is_true(vals[ARG_value].u_obj);
    pin_obj_t *p = claim_pin(type, id, P2_OWNER_PIN);
    configure_pin(p, mode, pull, value);
    return MP_OBJ_FROM_PTR(p);
}
static mp_obj_t value(size_t n, const mp_obj_t *args) {
    pin_obj_t *p = open_pin(args[0]);
    if (n == 1) {
        return MP_OBJ_NEW_SMALL_INT(sample(p->pin));
    }
    bool high = mp_obj_is_true(args[1]);
    p = open_pin(args[0]);
    if (p->mode == PIN_IN) {
        mp_raise_OSError(MP_EPERM);
    }
    write_latch(p->pin, high);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(value_obj, 1, 2, value);
static mp_obj_t pin_set(mp_obj_t self, bool high) {
    const mp_obj_t args[] = {self, mp_obj_new_bool(high)};
    return value(2, args);
}
static mp_obj_t on(mp_obj_t self) {
    return pin_set(self, true);
}
static mp_obj_t off(mp_obj_t self) {
    return pin_set(self, false);
}
static MP_DEFINE_CONST_FUN_OBJ_1(on_obj, on);
static MP_DEFINE_CONST_FUN_OBJ_1(off_obj, off);
static mp_obj_t pin_call(mp_obj_t self, size_t n, size_t nk, const mp_obj_t *args) {
    mp_arg_check_num(n, nk, 0, 1, false);
    if (!n) {
        return value(1, &self);
    }
    const mp_obj_t call_args[] = {self, args[0]};
    return value(2, call_args);
}
static const mp_rom_map_elem_t pin_locals[] = {
    #if P2_ENABLE_HW_IRQ
    {MP_ROM_QSTR(MP_QSTR_IRQ_RISING), MP_ROM_INT(P2_IRQ_RISING)},
    {MP_ROM_QSTR(MP_QSTR_IRQ_FALLING), MP_ROM_INT(P2_IRQ_FALLING)},
    {MP_ROM_QSTR(MP_QSTR_irq), MP_ROM_PTR(&p2_pin_irq_obj)},
    #endif
    {MP_ROM_QSTR(MP_QSTR_IN), MP_ROM_INT(PIN_IN)},
    {MP_ROM_QSTR(MP_QSTR_OUT), MP_ROM_INT(PIN_OUT)},
    {MP_ROM_QSTR(MP_QSTR_OPEN_DRAIN), MP_ROM_INT(PIN_OPEN_DRAIN)},
    {MP_ROM_QSTR(MP_QSTR_PULL_UP), MP_ROM_INT(PULL_UP)},
    {MP_ROM_QSTR(MP_QSTR_PULL_DOWN), MP_ROM_INT(PULL_DOWN)},
    {MP_ROM_QSTR(MP_QSTR_value), MP_ROM_PTR(&value_obj)},
    {MP_ROM_QSTR(MP_QSTR_on), MP_ROM_PTR(&on_obj)},
    {MP_ROM_QSTR(MP_QSTR_off), MP_ROM_PTR(&off_obj)},
    {MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&release_pin_obj)},
    {MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&release_pin_obj)},
};
static MP_DEFINE_CONST_DICT(pin_dict, pin_locals);
MP_DEFINE_CONST_OBJ_TYPE(p2_pin_type, MP_QSTR_Pin, MP_TYPE_FLAG_NONE, make_new, pin_make_new, call, pin_call, locals_dict, &pin_dict);

static mp_obj_t smart_make_new(const mp_obj_type_t *type, size_t n, size_t nk, const mp_obj_t *args) {
    mp_arg_check_num(n, nk, 2, 4, false);
    unsigned id = p2_arg_range(args[0], 63);
    uint32_t mode = p2_arg_word(args[1]);
    if ((mode & 0x3e) == 0x36 || (mode & 1)) {
        mp_raise_ValueError(MP_ERROR_TEXT("unsupported mode or reserved bit"));
    }
    uint32_t x = n > 2 ? p2_arg_word(args[2]) : 0, y = n > 3 ? p2_arg_word(args[3]) : 0;
    pin_obj_t *p = claim_pin(type, id, P2_OWNER_SMARTPIN);
    __asm__ volatile ("dirl %0\n\twrpin %1, %0\n\twxpin %2, %0\n\twypin %3, %0\n\tdirh %0"
        : : "r" (id), "r" (mode), "r" (x), "r" (y) : "memory");
    return MP_OBJ_FROM_PTR(p);
}
static mp_obj_t write_x(mp_obj_t self, mp_obj_t value) {
    uint32_t v = p2_arg_word(value);
    __asm__ volatile ("wxpin %0, %1" : : "r" (v), "r" ((unsigned)open_pin(self)->pin) : "memory");
    return mp_const_none;
}
static mp_obj_t write_y(mp_obj_t self, mp_obj_t value) {
    uint32_t v = p2_arg_word(value);
    __asm__ volatile ("wypin %0, %1" : : "r" (v), "r" ((unsigned)open_pin(self)->pin) : "memory");
    return mp_const_none;
}
static mp_obj_t smart_read(mp_obj_t self) {
    uint32_t result;
    __asm__ volatile ("rdpin %0, %1" : "=r" (result) : "r" ((unsigned)open_pin(self)->pin) : "memory");
    return mp_obj_new_int_from_uint(result);
}
static mp_obj_t smart_peek(mp_obj_t self) {
    uint32_t result;
    __asm__ volatile ("rqpin %0, %1" : "=r" (result) : "r" ((unsigned)open_pin(self)->pin));
    return mp_obj_new_int_from_uint(result);
}
static mp_obj_t smart_ready(mp_obj_t self) {
    return mp_obj_new_bool(sample(open_pin(self)->pin));
}
static MP_DEFINE_CONST_FUN_OBJ_2(write_x_obj, write_x);
static MP_DEFINE_CONST_FUN_OBJ_2(write_y_obj, write_y);
static MP_DEFINE_CONST_FUN_OBJ_1(smart_read_obj, smart_read);
static MP_DEFINE_CONST_FUN_OBJ_1(smart_peek_obj, smart_peek);
static MP_DEFINE_CONST_FUN_OBJ_1(smart_ready_obj, smart_ready);
static const mp_rom_map_elem_t smart_locals[] = {
    {MP_ROM_QSTR(MP_QSTR_write_x), MP_ROM_PTR(&write_x_obj)},
    {MP_ROM_QSTR(MP_QSTR_write_y), MP_ROM_PTR(&write_y_obj)},
    {MP_ROM_QSTR(MP_QSTR_read), MP_ROM_PTR(&smart_read_obj)},
    {MP_ROM_QSTR(MP_QSTR_peek), MP_ROM_PTR(&smart_peek_obj)},
    {MP_ROM_QSTR(MP_QSTR_ready), MP_ROM_PTR(&smart_ready_obj)},
    {MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&release_pin_obj)},
    {MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&release_pin_obj)},
    {MP_ROM_QSTR(MP_QSTR_NORMAL), MP_ROM_INT(0x0)},
    {MP_ROM_QSTR(MP_QSTR_REPOSITORY), MP_ROM_INT(0x2)},
    {MP_ROM_QSTR(MP_QSTR_DAC_NOISE), MP_ROM_INT(0x2)},
    {MP_ROM_QSTR(MP_QSTR_DAC_DITHER_RND), MP_ROM_INT(0x4)},
    {MP_ROM_QSTR(MP_QSTR_DAC_DITHER_PWM), MP_ROM_INT(0x6)},
    {MP_ROM_QSTR(MP_QSTR_PULSE), MP_ROM_INT(0x8)},
    {MP_ROM_QSTR(MP_QSTR_TRANSITION), MP_ROM_INT(0xa)},
    {MP_ROM_QSTR(MP_QSTR_NCO_FREQ), MP_ROM_INT(0xc)},
    {MP_ROM_QSTR(MP_QSTR_NCO_DUTY), MP_ROM_INT(0xe)},
    {MP_ROM_QSTR(MP_QSTR_PWM_TRIANGLE), MP_ROM_INT(0x10)},
    {MP_ROM_QSTR(MP_QSTR_PWM_SAWTOOTH), MP_ROM_INT(0x12)},
    {MP_ROM_QSTR(MP_QSTR_PWM_SMPS), MP_ROM_INT(0x14)},
    {MP_ROM_QSTR(MP_QSTR_QUADRATURE), MP_ROM_INT(0x16)},
    {MP_ROM_QSTR(MP_QSTR_REG_UP), MP_ROM_INT(0x18)},
    {MP_ROM_QSTR(MP_QSTR_REG_UP_DOWN), MP_ROM_INT(0x1a)},
    {MP_ROM_QSTR(MP_QSTR_COUNT_RISES), MP_ROM_INT(0x1c)},
    {MP_ROM_QSTR(MP_QSTR_COUNT_HIGHS), MP_ROM_INT(0x1e)},
    {MP_ROM_QSTR(MP_QSTR_STATE_TICKS), MP_ROM_INT(0x20)},
    {MP_ROM_QSTR(MP_QSTR_HIGH_TICKS), MP_ROM_INT(0x22)},
    {MP_ROM_QSTR(MP_QSTR_EVENTS_TICKS), MP_ROM_INT(0x24)},
    {MP_ROM_QSTR(MP_QSTR_PERIODS_TICKS), MP_ROM_INT(0x26)},
    {MP_ROM_QSTR(MP_QSTR_PERIODS_HIGHS), MP_ROM_INT(0x28)},
    {MP_ROM_QSTR(MP_QSTR_COUNTER_TICKS), MP_ROM_INT(0x2a)},
    {MP_ROM_QSTR(MP_QSTR_COUNTER_HIGHS), MP_ROM_INT(0x2c)},
    {MP_ROM_QSTR(MP_QSTR_COUNTER_PERIODS), MP_ROM_INT(0x2e)},
    {MP_ROM_QSTR(MP_QSTR_ADC), MP_ROM_INT(0x30)},
    {MP_ROM_QSTR(MP_QSTR_ADC_EXT), MP_ROM_INT(0x32)},
    {MP_ROM_QSTR(MP_QSTR_ADC_SCOPE), MP_ROM_INT(0x34)},
    {MP_ROM_QSTR(MP_QSTR_SYNC_TX), MP_ROM_INT(0x38)},
    {MP_ROM_QSTR(MP_QSTR_SYNC_RX), MP_ROM_INT(0x3a)},
    {MP_ROM_QSTR(MP_QSTR_ASYNC_TX), MP_ROM_INT(0x3c)},
    {MP_ROM_QSTR(MP_QSTR_ASYNC_RX), MP_ROM_INT(0x3e)},
    {MP_ROM_QSTR(MP_QSTR_OE), MP_ROM_INT(0x40)},
    {MP_ROM_QSTR(MP_QSTR_PLUS1_B), MP_ROM_INT(0x1000000)},
    {MP_ROM_QSTR(MP_QSTR_MINUS1_B), MP_ROM_INT(0x7000000)},
    {MP_ROM_QSTR(MP_QSTR_ADC_1X), MP_ROM_INT(0x118000)},
    {MP_ROM_QSTR(MP_QSTR_ADC_GIO), MP_ROM_INT(0x100000)},
    {MP_ROM_QSTR(MP_QSTR_ADC_VIO), MP_ROM_INT(0x108000)},
    {MP_ROM_QSTR(MP_QSTR_DAC_990R_3V), MP_ROM_INT(0x140000)},
};
static MP_DEFINE_CONST_DICT(smart_dict, smart_locals);
MP_DEFINE_CONST_OBJ_TYPE(p2_smartpin_type, MP_QSTR_SmartPin, MP_TYPE_FLAG_NONE,
    make_new, smart_make_new, locals_dict, &smart_dict);
