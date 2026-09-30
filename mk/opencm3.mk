export OPENCM3_DIR := $(CURDIR)/libopencm3
DEVICES_DATA ?= $(OPENCM3_DIR)/ld/devices.data

genlink_family := $(shell $(OPENCM3_DIR)/scripts/genlink.py $(DEVICES_DATA) $(DEVICE) FAMILY)
genlink_cpu := $(shell $(OPENCM3_DIR)/scripts/genlink.py $(DEVICES_DATA) $(DEVICE) CPU)
genlink_fpu := $(shell $(OPENCM3_DIR)/scripts/genlink.py $(DEVICES_DATA) $(DEVICE) FPU)
genlink_cppflags := $(shell $(OPENCM3_DIR)/scripts/genlink.py $(DEVICES_DATA) $(DEVICE) CPPFLAGS)

CPPFLAGS += $(genlink_cppflags) -I$(OPENCM3_DIR)/include
LDFLAGS += -L$(OPENCM3_DIR)/lib

ARCH_FLAGS := -mcpu=$(genlink_cpu)
ifeq ($(genlink_cpu),$(filter $(genlink_cpu),cortex-m0 cortex-m0plus cortex-m3 cortex-m4 cortex-m7))
ARCH_FLAGS += -mthumb
endif

ifeq ($(genlink_fpu),soft)
ARCH_FLAGS += -msoft-float
else ifeq ($(genlink_fpu),hard-fpv4-sp-d16)
ARCH_FLAGS += -mfloat-abi=hard -mfpu=fpv4-sp-d16
else ifeq ($(genlink_fpu),hard-fpv5-sp-d16)
ARCH_FLAGS += -mfloat-abi=hard -mfpu=fpv5-sp-d16
endif

CFLAGS += $(ARCH_FLAGS) -std=gnu11
LDFLAGS += \
	$(ARCH_FLAGS) \
	--specs=nosys.specs \
	-Wl,--wrap=_sbrk \
	-Wl,-u,__wrap__sbrk \
	-Wl,--wrap=_close \
	-Wl,--wrap=_isatty \
	-Wl,--wrap=_kill \
	-Wl,--wrap=_lseek \
	-Wl,--wrap=_read \
	-Wl,--wrap=_write \
	-Wl,--wrap=_fstat \
	-Wl,--wrap=_getpid \
	-nostartfiles \
	-ffreestanding \
	-T$(LDSCRIPT)

LIBNAME := opencm3_$(genlink_family)
LDLIBS += -l$(LIBNAME) -lc -lgcc
LIBDEPS += $(OPENCM3_DIR)/lib/lib$(LIBNAME).a
COMPILEDEPS += $(OPENCM3_DIR)/lib/lib$(LIBNAME).a

$(OPENCM3_DIR)/lib/lib$(LIBNAME).a:
	$(MAKE) -C $(OPENCM3_DIR) $(OPENCM3_TARGET)

ifeq ($(wildcard ldscripts/$(PLATFORM).ld),)
LDSCRIPT = obj/generated.$(DEVICE).ld
$(LDSCRIPT): $(OPENCM3_DIR)/ld/linker.ld.S $(DEVICES_DATA)
	@printf '  GENLNK  $(DEVICE)\n'
	$(Q)mkdir -p $(@D)
	$(Q)$(CPP) $(ARCH_FLAGS) $(shell $(OPENCM3_DIR)/scripts/genlink.py $(DEVICES_DATA) $(DEVICE) DEFS) -P -E $< -o $@
else
LDSCRIPT = ldscripts/$(PLATFORM).ld
endif

.PHONY: libclean

libclean:
	$(MAKE) -C $(OPENCM3_DIR) clean
