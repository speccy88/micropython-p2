// SPDX-License-Identifier: MIT
#pragma once
#ifndef P2_ENABLE_BUSES
#define P2_ENABLE_BUSES (0)
#endif
#if P2_ENABLE_BUSES
#define MICROPY_PY_MACHINE_SOFTI2C (1)
#define MICROPY_PY_MACHINE_SPI (1)
#endif
