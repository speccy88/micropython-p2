// The standalone bootstrap sets 160 MHz without the SDK's hub 0x14 clock word.
#include <propeller.h>
#include <sys/ff.h>
#undef CLKFREQ
#define CLKFREQ 160000000u
