BOARD ?= P2_EC32MB
PROFILE ?= edge
BUILD ?= build-$(BOARD)-$(PROFILE)
include ../../py/mkenv.mk
P2_WORK ?= $(HOME)/tinygo-p2-work
P2_BIN ?= $(P2_WORK)/llvm15-build/bin
CC = $(P2_BIN)/clang
LD = $(P2_BIN)/ld.lld
OBJCOPY = $(P2_BIN)/llvm-objcopy
P2_FLAGS = --target=p2 -ffreestanding -fno-builtin -fno-jump-tables -fno-unwind-tables -fno-asynchronous-unwind-tables -ffunction-sections -fdata-sections
# Console-only smoke image has no dependency on the VM or a C library.
.PHONY: console
console: $(BUILD)/console.elf
$(BUILD)/console.elf: startup.c boot.S tests/console.c p2.ld
	@mkdir -p $(BUILD)
	$(CC) $(P2_FLAGS) -Os -c startup.c -o $(BUILD)/console-start.o
	$(CC) $(P2_FLAGS) -c boot.S -o $(BUILD)/console-boot.o
	$(CC) $(P2_FLAGS) -Os -c tests/console.c -o $(BUILD)/console-main.o
	$(LD) --gc-sections -T p2.ld $(addprefix $(BUILD)/console-,boot.o start.o main.o) -o $@

ifneq ($(MAKECMDGOALS),console)
include runtime/runtime.mk
QSTR_DEFS = qstrdefsport.h
FROZEN_MANIFEST ?= $(if $(filter edge,$(PROFILE)),manifest.py,)
MICROPY_ROM_TEXT_COMPRESSION ?= 0
ifeq ($(PROFILE),edge)
MICROPY_VFS_FAT = 1
MICROPY_VFS_LFS2 = 1
else ifeq ($(PROFILE),threaded)
else ifneq ($(PROFILE),lean)
$(error Unknown PROFILE $(PROFILE))
endif
ifeq ($(wildcard boards/$(BOARD)/mpconfigboard.mk),)
$(error Unknown BOARD $(BOARD))
endif
include boards/$(BOARD)/mpconfigboard.mk
include $(TOP)/py/py.mk
include $(TOP)/extmod/extmod.mk
CSUPEROPT = -Oz
INC += -I. -I$(TOP) -I$(BUILD) $(P2_RUNTIME_INC)
CFLAGS += $(P2_FLAGS) $(INC) $(BOARD_FLAGS) -std=gnu11 -Oz -DNDEBUG -Wall -Werror=vla $(CFLAGS_EXTRA)
CFLAGS += -DP2_PROFILE_EDGE=$(if $(filter edge,$(PROFILE)),1,0)
CFLAGS += -DP2_PROFILE_THREADED=$(if $(filter threaded,$(PROFILE)),1,0)
CFLAGS += -DP2_ENABLE_BUSES=$(if $(filter edge,$(PROFILE)),1,0)
# Pinned P2 LLVM at -Oz clobbers the sentinel comparison flags in
# mp_set_lookup with the free-slot comparison. Keep maps/sets correct while
# using this compiler. The corrected compiler supports P2_MAP_OPT=-Oz.
P2_MAP_OPT ?= -Os
$(BUILD)/py/map.o: private CFLAGS += $(P2_MAP_OPT)
$(BUILD)/py/map.o: Makefile
CFLAGS_MCU = --target=p2
SRC_C += main.c mphalport.c startup.c $(wildcard drivers/*.c) $(wildcard storage/*.c) $(wildcard bus/*.c)
SRC_C += shared/readline/readline.c shared/runtime/pyexec.c shared/runtime/stdout_helpers.c shared/runtime/sys_stdio_mphal.c shared/timeutils/timeutils.c
ifneq ($(PROFILE),threaded)
SRC_C += timer.c shared/runtime/softtimer.c shared/runtime/mpirq.c
endif
SRC_QSTR += $(SRC_C)
SRC_C += $(P2_RUNTIME_C)
SRC_S += boot.S gc_p2.S $(wildcard drivers/*.S) $(wildcard bus/*.S) $(P2_RUNTIME_S)
ifeq ($(PROFILE),threaded)
SRC_C := $(filter-out drivers/% storage/% bus/%,$(SRC_C)) thread.c
SRC_S := $(filter-out drivers/% bus/%,$(SRC_S)) thread_p2.S
endif
OBJ += $(PY_O) $(addprefix $(BUILD)/,$(SRC_C:.c=.o) $(SRC_S:.S=.o))
all: $(BUILD)/firmware.bin
$(BUILD)/firmware.elf: $(OBJ) $(P2_RUNTIME_LIBS) p2.ld
	$(LD) --gc-sections -Map=$@.map -T p2.ld -o $@ $(OBJ) $(P2_RUNTIME_LIBS)
$(BUILD)/firmware.bin: $(BUILD)/firmware.elf
	$(OBJCOPY) -O binary $< $@
include $(TOP)/py/mkrules.mk
endif
