# From ports/p2: make -f tests/sd_independent/Makefile
BUILD ?= build-sd-independent
TOP = ../..
.DEFAULT_GOAL := all
include runtime/runtime.mk
SDK_DRIVERS := $(P2_WORK)/p2llvm/libc/drivers
CC := $(P2_LLVM_BIN)/clang
OPTIONS := --target=p2 -Os -ffreestanding -fno-builtin -ffunction-sections -fdata-sections \
    $(P2_RUNTIME_INC) -I$(P2_WORK)/p2llvm/libp2/include -I$(SDK_DRIVERS) -I$(TOP)/lib/crypto-algorithms
OBJECTS := $(addprefix $(BUILD)/,boot.o startup.o sdmmc.o sha256.o diagnostic.o memory.o memcmp.o)
all: $(BUILD)/diagnostic.bin
$(BUILD)/boot.o: boot.S
$(BUILD)/startup.o: startup.c
$(BUILD)/memory.o: runtime/memory.S
$(BUILD)/memcmp.o: $(P2_WORK)/p2llvm/libc/string/memcmp.c
$(BUILD)/diagnostic.o: tests/sd_independent/diagnostic.c
$(BUILD)/sha256.o: $(TOP)/lib/crypto-algorithms/sha256.c
$(BUILD)/sha256.o: private OPTIONS += -include stdint.h -include string.h
$(BUILD)/sdmmc.o: $(SDK_DRIVERS)/sdmmc.c tests/sd_independent/sdk-clock.h
$(BUILD)/sdmmc.o: private OPTIONS += -include tests/sd_independent/sdk-clock.h
$(OBJECTS):
	@mkdir -p "$(@D)"
	$(CC) $(OPTIONS) -MMD -MP -c "$<" -o "$@"
$(BUILD)/diagnostic.elf: $(OBJECTS) $(P2_BUILTINS) p2.ld
	$(P2_LLVM_BIN)/ld.lld --gc-sections -Map=$@.map -T p2.ld -o "$@" $(OBJECTS) $(P2_BUILTINS)
	! $(P2_LLVM_BIN)/llvm-nm "$@" | grep -E ' sd_xmit_datablock$$| disk_write$$| f_write$$'
$(BUILD)/diagnostic.bin: $(BUILD)/diagnostic.elf
	$(P2_LLVM_BIN)/llvm-objcopy -O binary "$<" "$@"
-include $(OBJECTS:.o=.d)
