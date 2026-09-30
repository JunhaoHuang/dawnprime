.DEFAULT_GOAL := all

COMPILEDEPS += crypto_kem/common/r2_radix16_mul_generated.inc

.PHONY: all clean help libclean list schemes qemu-run platform-sync r2-generated-check

include mk/config.mk
include mk/$(PLATFORM).mk
include mk/scheme.mk

SHORT_TARGETS := $(ELFS:elf/%.elf=%)
REQUESTED_SHORT_TARGETS := $(filter $(SHORT_TARGETS),$(MAKECMDGOALS))
REQUESTED_ELFS := $(addprefix elf/,$(addsuffix .elf,$(REQUESTED_SHORT_TARGETS)))
QEMU_ELFS := $(if $(REQUESTED_ELFS),$(REQUESTED_ELFS),$(ELFS))

.PHONY: $(SHORT_TARGETS)

all: platform-sync $(BINS)

$(SHORT_TARGETS): %: platform-sync bin/%.bin

platform-sync:
	@prev=''; \
	current='PLATFORM=$(PLATFORM) OPT=$(OPT) LTO=$(LTO) NGCC_ITERATIONS=$(NGCC_ITERATIONS) USE_SM3_ASM=$(USE_SM3_ASM) USE_KECCAK=$(USE_KECCAK)$(if $(strip $(DKEX_SIG_MLDSA_BUILD_CONFIG)), $(DKEX_SIG_MLDSA_BUILD_CONFIG))'; \
	if [ -f $(PLATFORM_STATE) ]; then \
		prev=$$(cat $(PLATFORM_STATE)); \
	fi; \
	if [ "$$prev" != "" ] && [ "$$prev" != "$$current" ]; then \
		printf '  CLEAN   build config changed: %s -> %s\n' "$$prev" "$$current"; \
		rm -rf bin elf obj; \
	fi; \
	printf '%s\n' "$$current" > $(PLATFORM_STATE)

list schemes:
	@printf '%s\n' $(SCHEMES)

r2-generated-check:
	python3 crypto_kem/common/verify_r2_radix16.py

help:
	@printf 'Usage: make [all|<output-stem>] [PLATFORM=<platform>] [FAMILY=<family>] [SCHEME=<scheme>] [IMPLEMENTATION=<impl>] [APP=<name>]\n'
	@printf 'Example shorthand target: make crypto_kem_DKE-128_ref_test\n'
	@printf 'Supported platforms: %s\n' "$(SUPPORTED_PLATFORMS)"
	@printf 'Supported families: %s\n' "$(SUPPORTED_FAMILIES)"
	@printf 'Available implementations:\n'
	@printf '  %s\n' $(SCHEMES)
	@printf 'Available apps: %s\n' "$(SUPPORTED_APPS)"

qemu-run: platform-sync $(QEMU_ELFS)
	@if [ "$(PLATFORM)" != "mps2-an386" ]; then \
		printf 'qemu-run is only supported for PLATFORM=mps2-an386\n' >&2; \
		exit 1; \
	fi
	@if [ "$(words $(QEMU_ELFS))" != "1" ]; then \
		printf 'qemu-run requires exactly one target; use a shorthand target or FAMILY=..., SCHEME=..., IMPLEMENTATION=..., and APP=...\n' >&2; \
		exit 1; \
	fi
	$(Q)$(QEMU) $(QEMUFLAGS) -kernel $(firstword $(QEMU_ELFS))

clean: libclean
	rm -rf bin elf obj $(PLATFORM_STATE)

.SECONDARY:
