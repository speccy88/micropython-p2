BOARD ?= P2_EC32MB
PROFILE ?= edge
P2_ENABLE_HW_IRQ ?= 0
ifneq ($(P2_ENABLE_HW_IRQ),0)
ifneq ($(P2_ENABLE_HW_IRQ),1)
$(error P2_ENABLE_HW_IRQ must be 0 or 1)
endif
ifeq ($(PROFILE),threaded)
$(error P2_ENABLE_HW_IRQ=1 is unsupported with PROFILE=threaded)
endif
endif
BUILD ?= build-$(BOARD)-$(PROFILE)$(if $(filter 1,$(P2_ENABLE_HW_IRQ)),-irq)
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
MICROPY_ROM_TEXT_COMPRESSION ?= $(if $(filter edge,$(PROFILE)),1,0)
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
# Direct bytecode dispatch saves hub instruction fetches on the full Edge VM.
# Other profiles retain their measured size/dispatch tradeoff.
ifeq ($(PROFILE),edge)
$(BUILD)/py/vm.o: private CFLAGS += -DMICROPY_OPT_COMPUTED_GOTO=1
endif
$(BUILD)/py/map.o: Makefile
CFLAGS_MCU = --target=p2
SRC_C += main.c mphalport.c startup.c $(wildcard drivers/*.c) $(wildcard storage/*.c) $(wildcard bus/*.c)
SRC_C += shared/readline/readline.c shared/runtime/pyexec.c shared/runtime/stdout_helpers.c shared/runtime/sys_stdio_mphal.c shared/timeutils/timeutils.c
ifneq ($(PROFILE),threaded)
SRC_C += timer.c shared/runtime/softtimer.c shared/runtime/mpirq.c
endif
# Upstream qstr/root extraction retains per-source fragments across incremental
# builds. Keep enabled and disabled inventories separate, even with BUILD set.
IRQ_CFG = $(BUILD)/p2_irq_config.h
.PHONY: p2-force-config
$(IRQ_CFG): p2-force-config
	@mkdir -p $(BUILD)
	@if test -f $@; then \
	    echo '#define P2_ENABLE_HW_IRQ $(P2_ENABLE_HW_IRQ)' | cmp -s - $@ || \
	        { echo "IRQ configuration differs: choose a separate BUILD directory" >&2; exit 1; }; \
	else echo '#define P2_ENABLE_HW_IRQ $(P2_ENABLE_HW_IRQ)' > $@; fi
CFLAGS += -include $(IRQ_CFG)
QSTR_GLOBAL_DEPENDENCIES += $(IRQ_CFG)
.DELETE_ON_ERROR:
ifeq ($(P2_ENABLE_HW_IRQ),1)
SRC_C += irq.c
SRC_S += irq_p2.S
endif
SRC_QSTR += $(SRC_C)
SRC_C += $(P2_RUNTIME_C)
SRC_S += boot.S gc_p2.S $(wildcard drivers/*.S) $(wildcard bus/*.S) $(P2_RUNTIME_S)
ifeq ($(PROFILE),threaded)
SRC_C := $(filter-out drivers/% storage/% bus/%,$(SRC_C)) thread.c
SRC_S := $(filter-out drivers/% bus/%,$(SRC_S)) thread_p2.S
# The worker only exchanges words with managed native service cogs. GPIO
# configuration and handle lifetime remain with the primary interpreter.
SRC_C += drivers/modp2.c drivers/hubdriver.c drivers/resources.c
SRC_S += drivers/counter.S
endif
OBJ += $(PY_O) $(addprefix $(BUILD)/,$(SRC_C:.c=.o) $(SRC_S:.S=.o))
$(OBJ): $(IRQ_CFG)
all: $(BUILD)/firmware.bin
$(BUILD)/firmware.elf: $(OBJ) $(P2_RUNTIME_LIBS) p2.ld
	$(LD) --gc-sections -Map=$@.map -T p2.ld -o $@ $(OBJ) $(P2_RUNTIME_LIBS)
ifeq ($(P2_ENABLE_HW_IRQ),1)
	$(PYTHON) tests/check_irq_asm.py --bin $(P2_BIN) $@ $(BUILD)/irq_p2.o
$(BUILD)/firmware.elf: tests/check_irq_asm.py
endif
$(BUILD)/firmware.bin: $(BUILD)/firmware.elf
	$(OBJCOPY) -O binary $< $@
include $(TOP)/py/mkrules.mk
endif
