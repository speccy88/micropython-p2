// SPDX-License-Identifier: MIT
#pragma once
#if P2_ENABLE_BUSES
extern const mp_obj_type_t p2_uart_type, p2_soft_spi_type, p2_soft_i2c_type;
#define P2_MACHINE_BUS_GLOBALS \
    {MP_ROM_QSTR(MP_QSTR_UART), MP_ROM_PTR(&p2_uart_type)}, \
    {MP_ROM_QSTR(MP_QSTR_SoftSPI), MP_ROM_PTR(&p2_soft_spi_type)}, \
    {MP_ROM_QSTR(MP_QSTR_SoftI2C), MP_ROM_PTR(&p2_soft_i2c_type)},
#else
#define P2_MACHINE_BUS_GLOBALS
#endif
