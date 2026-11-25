// SPDX-License-Identifier: MIT
#include <math.h>

// The IEC 60559 implementation-defined NaN payload is canonical on P2.
float nanf(const char *tag) {
    (void)tag;
    return __builtin_nanf("");
}
