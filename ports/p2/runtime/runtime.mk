# Included from ports/p2/Makefile. BUILD should be specific to this profile.
P2_WORK ?= $(HOME)/tinygo-p2-work
P2_LLVM_BIN ?= $(P2_WORK)/llvm15-build/bin
P2_RUNTIME_C :=
P2_RUNTIME_S := runtime/context.S runtime/memory.S
P2_RUNTIME_INC := -Iruntime/include -idirafter $(P2_WORK)/p2llvm/libc/include
P2_SUPPORT := $(BUILD)/support
P2_BUILTINS := $(P2_SUPPORT)/builtins/lib/builtins/libcompiler_builtins.a
P2_LIBC := $(P2_SUPPORT)/libp2c.a
P2_RUNTIME_LIBS := $(P2_LIBC) $(P2_BUILTINS)

$(P2_BUILTINS): $(wildcard $(P2_WORK)/p2llvm/libp2/lib/builtins/*)
	cmake -S "$(P2_WORK)/p2llvm/libp2" -B "$(P2_SUPPORT)/builtins" -G Ninja -Dllvm="$(P2_LLVM_BIN)"
	cmake --build "$(P2_SUPPORT)/builtins" --target compiler_builtins

P2_STRING_NAMES := memchr memcmp strchr strcmp strcpy strlen strncmp strncpy strrchr strstr
P2_C_SOURCES := $(addprefix $(P2_WORK)/p2llvm/libc/string/,$(addsuffix .c,$(P2_STRING_NAMES)))
P2_MATH_SOURCES := $(filter-out %/thumb_vfp_sqrtf.c,$(wildcard $(TOP)/lib/libm/*.c)) $(P2_WORK)/p2llvm/libc/math/s_fabsf.c
P2_SUPPORT_SOURCES := $(P2_C_SOURCES) $(P2_MATH_SOURCES)
P2_SUPPORT_OBJECTS := $(addprefix $(P2_SUPPORT)/,$(notdir $(P2_SUPPORT_SOURCES:.c=.o)))
# The float library and string library have distinct basenames.
$(P2_SUPPORT)/%.o: $(P2_WORK)/p2llvm/libc/string/%.c
	@mkdir -p "$(@D)"
	$(P2_LLVM_BIN)/clang -target p2 -Oz -ffreestanding -fno-builtin -ffunction-sections -fdata-sections $(P2_RUNTIME_INC) -Wno-deprecated-non-prototype -MMD -MP -c "$<" -o "$@"

$(P2_SUPPORT)/%.o: $(TOP)/lib/libm/%.c
	@mkdir -p "$(@D)"
	$(P2_LLVM_BIN)/clang -target p2 -Oz -ffreestanding -fno-builtin -ffunction-sections -fdata-sections $(P2_RUNTIME_INC) -MMD -MP -c "$<" -o "$@"

$(P2_SUPPORT)/s_fabsf.o: $(P2_WORK)/p2llvm/libc/math/s_fabsf.c
	@mkdir -p "$(@D)"
	$(P2_LLVM_BIN)/clang -target p2 -Oz -ffreestanding -fno-builtin $(P2_RUNTIME_INC) -MMD -MP -c "$<" -o "$@"

$(P2_LIBC): $(P2_SUPPORT_OBJECTS)
	$(P2_LLVM_BIN)/llvm-ar rcs "$@" $^

-include $(P2_SUPPORT_OBJECTS:.o=.d)
