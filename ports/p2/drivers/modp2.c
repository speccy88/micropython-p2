// SPDX-License-Identifier: MIT
#include "modp2.h"
#if P2_ENABLE_HW_IRQ
#include "irq.h"
#endif
#include "bus/machine_bus.h"
void p2_poll_borrowed_io(void) {
    p2_console_poll_interrupt();
    mp_obj_t exc = MP_STATE_THREAD(mp_pending_exception);
    if (exc != MP_OBJ_NULL) {
        MP_STATE_THREAD(mp_pending_exception) = MP_OBJ_NULL;
        nlr_raise(exc);
    }
}
extern const mp_obj_type_t p2_pwm_type, p2_adc_type, p2_dac_type;
extern const mp_obj_type_t p2_timer_type;
extern const mp_obj_type_t p2_driver_type;
extern const mp_obj_fun_builtin_fixed_t p2_get_driver_obj;
#if MICROPY_VFS_FAT
extern const mp_obj_type_t p2_sdcard_type;
#endif
#if MICROPY_VFS_LFS2
extern const mp_obj_type_t p2_flash_type;
#endif
static mp_obj_t cycles(void) {
    return mp_obj_new_int_from_uint(p2_ct());
}
static MP_DEFINE_CONST_FUN_OBJ_0(cycles_obj, cycles);
static mp_obj_t owner(mp_obj_t pin) {
    static const qstr names[] = { MP_QSTR_free, MP_QSTR_pin, MP_QSTR_smartpin, MP_QSTR_sd, MP_QSTR_psram, MP_QSTR_console,
                                  MP_QSTR_uart, MP_QSTR_spi, MP_QSTR_i2c, MP_QSTR_flash, MP_QSTR_driver };
    return MP_OBJ_NEW_QSTR(names[p2_pin_owner(p2_arg_range(pin, 63))]);
}
static MP_DEFINE_CONST_FUN_OBJ_1(owner_obj, owner);
static const mp_rom_map_elem_t p2_globals[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_p2)},
    #if !P2_PROFILE_THREADED
    {MP_ROM_QSTR(MP_QSTR_SmartPin), MP_ROM_PTR(&p2_smartpin_type)},
    {MP_ROM_QSTR(MP_QSTR_Cog), MP_ROM_PTR(&p2_cog_type)},
    #endif
    {MP_ROM_QSTR(MP_QSTR_Driver), MP_ROM_PTR(&p2_driver_type)},
    {MP_ROM_QSTR(MP_QSTR_get_driver), MP_ROM_PTR(&p2_get_driver_obj)},
    #if MICROPY_VFS_LFS2
    {MP_ROM_QSTR(MP_QSTR_Flash), MP_ROM_PTR(&p2_flash_type)},
    #endif
    #if P2_BOARD_HAS_PSRAM && !P2_PROFILE_THREADED
    {MP_ROM_QSTR(MP_QSTR_PSRAM), MP_ROM_PTR(&p2_psram_type)},
    #endif
    {MP_ROM_QSTR(MP_QSTR_cycles), MP_ROM_PTR(&cycles_obj)},
    {MP_ROM_QSTR(MP_QSTR_pin_owner), MP_ROM_PTR(&owner_obj)},
    {MP_ROM_QSTR(MP_QSTR_CLOCK_HZ), MP_ROM_INT(P2_CLOCK_HZ)},
};
static MP_DEFINE_CONST_DICT(p2_dict, p2_globals);
const mp_obj_module_t p2_module = { .base = { &mp_type_module }, .globals = (mp_obj_dict_t *)&p2_dict };
MP_REGISTER_MODULE(MP_QSTR_p2, p2_module);
#if !P2_PROFILE_THREADED
static mp_obj_t machine_freq(void) {
    return MP_OBJ_NEW_SMALL_INT(P2_CLOCK_HZ);
}
static MP_DEFINE_CONST_FUN_OBJ_0(machine_freq_obj, machine_freq);
static const mp_rom_map_elem_t machine_globals[] = {
    P2_MACHINE_BUS_GLOBALS
    #if P2_ENABLE_HW_IRQ
    {MP_ROM_QSTR(MP_QSTR_disable_irq), MP_ROM_PTR(&p2_disable_irq_obj)},
    {MP_ROM_QSTR(MP_QSTR_enable_irq), MP_ROM_PTR(&p2_enable_irq_obj)},
    #endif
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_machine)},
    {MP_ROM_QSTR(MP_QSTR_Pin), MP_ROM_PTR(&p2_pin_type)},
    {MP_ROM_QSTR(MP_QSTR_PWM), MP_ROM_PTR(&p2_pwm_type)},
    {MP_ROM_QSTR(MP_QSTR_Timer), MP_ROM_PTR(&p2_timer_type)},
    {MP_ROM_QSTR(MP_QSTR_ADC), MP_ROM_PTR(&p2_adc_type)},
    {MP_ROM_QSTR(MP_QSTR_DAC), MP_ROM_PTR(&p2_dac_type)},
    #if MICROPY_VFS_FAT
    {MP_ROM_QSTR(MP_QSTR_SDCard), MP_ROM_PTR(&p2_sdcard_type)},
    #endif
    {MP_ROM_QSTR(MP_QSTR_freq), MP_ROM_PTR(&machine_freq_obj)},
};
static MP_DEFINE_CONST_DICT(machine_dict, machine_globals);
const mp_obj_module_t p2_machine_module = { .base = { &mp_type_module }, .globals = (mp_obj_dict_t *)&machine_dict };
MP_REGISTER_MODULE(MP_QSTR_machine, p2_machine_module);
#endif
