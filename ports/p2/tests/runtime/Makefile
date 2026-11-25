# Run from ports/p2: make -f tests/runtime/Makefile
BUILD ?= build-runtime
TOP = ../..
.DEFAULT_GOAL := all
include runtime/runtime.mk
CC = $(P2_LLVM_BIN)/clang
CFLAGS = --target=p2 -ffreestanding -fno-builtin -Werror=vla -Os -ffunction-sections -fdata-sections $(P2_RUNTIME_INC)
SRCS := boot.S startup.c runtime/context.S runtime/memory.S tests/runtime/registers.S tests/runtime/check.c
OBJS := $(addprefix $(BUILD)/,$(addsuffix .o,$(SRCS)))
$(BUILD)/%.o: %
	@mkdir -p "$(@D)"
	$(CC) $(CFLAGS) -MMD -MP -c "$<" -o "$@"

all: $(BUILD)/foundation.bin
$(BUILD)/foundation.bin: $(BUILD)/foundation.elf
	$(P2_LLVM_BIN)/llvm-objcopy -O binary "$<" "$@"

$(BUILD)/foundation.elf: $(OBJS) $(P2_RUNTIME_LIBS) p2.ld
	$(P2_LLVM_BIN)/ld.lld --gc-sections -T p2.ld -Map=$@.map -o "$@" $(OBJS) $(P2_RUNTIME_LIBS)

-include $(OBJS:.o=.d)
