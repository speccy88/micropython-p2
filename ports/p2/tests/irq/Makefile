# Invoke from ports/p2, using the same pinned toolchain as the main port.
BUILD ?= build-irq-native
TOP = ../..
.DEFAULT_GOAL := all
include runtime/runtime.mk
CC = $(P2_LLVM_BIN)/clang
CFLAGS = --target=p2 -Os -ffreestanding -fno-builtin -ffunction-sections -fdata-sections -I. $(P2_RUNTIME_INC)
SRCS := boot.S startup.c runtime/memory.S irq_p2.S tests/irq/context.S tests/irq/waits.S tests/irq/native.c
OBJS := $(addprefix $(BUILD)/,$(addsuffix .o,$(SRCS)))
$(BUILD)/%.o: %
	@mkdir -p "$(@D)"
	$(CC) $(CFLAGS) -MMD -MP -c "$<" -o "$@"

all: $(BUILD)/irq-native.bin
$(BUILD)/irq-native.bin: $(BUILD)/irq-native.elf
	$(P2_LLVM_BIN)/llvm-objcopy -O binary "$<" "$@"

$(BUILD)/irq-native.elf: $(OBJS) $(P2_BUILTINS) p2.ld
	$(P2_LLVM_BIN)/ld.lld --gc-sections -T p2.ld -Map=$@.map -o "$@" $(OBJS) $(P2_BUILTINS)

-include $(OBJS:.o=.d)
