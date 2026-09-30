ARCH_FLAGS += -mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16

CPPFLAGS += -DMPS2_AN386
CFLAGS += $(ARCH_FLAGS)
LDFLAGS += \
	$(ARCH_FLAGS) \
	--specs=nosys.specs \
	-Wl,--wrap=_sbrk \
	-Wl,-u,__wrap__sbrk \
	-Wl,--wrap=_open \
	-Wl,--wrap=_close \
	-Wl,--wrap=_isatty \
	-Wl,--wrap=_kill \
	-Wl,--wrap=_lseek \
	-Wl,--wrap=_read \
	-Wl,--wrap=_write \
	-Wl,--wrap=_fstat \
	-Wl,--wrap=_getpid \
	-ffreestanding \
	-T$(LDSCRIPT)
LDLIBS += -lc -lgcc

PLATFORM_LIB_SRCS := \
	common/hal-mps2.c \
	common/mps2/startup_MPS2.S

PLATFORM_INCLUDE_DIRS := \
	common/mps2

LDSCRIPT := obj/ldscript.ld

$(LDSCRIPT): common/mps2/MPS2.ld
	@printf '  GENLNK  $@\n'
	$(Q)mkdir -p $(@D)
	$(Q)$(CC) -x assembler-with-cpp -E -Wp,-P $(CPPFLAGS) -Icommon/mps2 $< -o $@

QEMUFLAGS := -M mps2-an386 -nographic -semihosting
