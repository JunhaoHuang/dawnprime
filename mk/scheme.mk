define family_tag
$(patsubst crypto_%,%,$(1))
endef

define family_of_impl
$(word 1,$(subst /, ,$(1)))
endef

define scheme_of_impl
$(word 2,$(subst /, ,$(1)))
endef

define implementation_of_impl
$(word 3,$(subst /, ,$(1)))
endef

define family_entry
$(strip $(ENTRY_$(call family_tag,$(1))))
endef

define family_app_sources
$(strip $(APP_SRCS_$(call family_tag,$(1))))
endef

define family_available_apps
$(basename $(notdir $(call family_app_sources,$(1))))
endef

IMPLS := $(sort $(foreach family,$(SUPPORTED_FAMILIES),$(patsubst %/,%,$(dir $(wildcard $(family)/*/*/$(call family_entry,$(family)))))))

ifneq ($(strip $(FAMILY)),)
IMPLS := $(filter $(FAMILY)/%,$(IMPLS))
endif

ifneq ($(strip $(SCHEME)),)
IMPLS := $(foreach impl,$(IMPLS),$(if $(filter $(SCHEME),$(call scheme_of_impl,$(impl))),$(impl)))
endif

ifneq ($(strip $(IMPLEMENTATION)),)
IMPLS := $(foreach impl,$(IMPLS),$(if $(filter $(IMPLEMENTATION),$(call implementation_of_impl,$(impl))),$(impl)))
endif

SCHEMES := $(patsubst %/,%,$(IMPLS))
SUPPORTED_APPS := $(sort $(foreach family,$(SUPPORTED_FAMILIES),$(call family_available_apps,$(family))))

define dkex_sig_mldsa_impl
$(wildcard $(1)/dkex_sig_mldsa.c)
endef

DKEX_SIG_MLDSA_IMPLS := $(foreach impl,$(IMPLS),$(if $(call dkex_sig_mldsa_impl,$(impl)),$(impl)))
DKEX_SIG_MLDSA_SRCS := $(sort $(wildcard crypto_sign/dilithium/ref/*.c))

ifneq ($(strip $(DKEX_SIG_MLDSA_IMPLS)),)
ifeq ($(filter $(DKEX_SIG_MLDSA_LEVEL),2 3 5),)
$(error Unsupported DKEX_SIG_MLDSA_LEVEL '$(DKEX_SIG_MLDSA_LEVEL)'; use 2, 3, or 5)
endif
endif

DKEX_SIG_MLDSA_BUILD_CONFIG := $(if $(strip $(DKEX_SIG_MLDSA_IMPLS)),DKEX_SIG_MLDSA_LEVEL=$(DKEX_SIG_MLDSA_LEVEL))

ifneq ($(strip $(APP)),)
ifneq ($(strip $(FAMILY)),)
ifeq ($(filter $(APP),$(call family_available_apps,$(FAMILY))),)
$(error Unsupported APP '$(APP)' for FAMILY '$(FAMILY)'; available apps: $(call family_available_apps,$(FAMILY)))
endif
else
ifeq ($(filter $(APP),$(SUPPORTED_APPS)),)
$(error Unsupported APP '$(APP)'; available apps: $(SUPPORTED_APPS))
endif
endif
endif

define selected_apps_for_impl
$(if $(strip $(APP)),$(filter $(APP),$(call family_available_apps,$(call family_of_impl,$(1)))),$(call family_available_apps,$(call family_of_impl,$(1))))
endef

define impl_name
$(subst /,_,$(1))
endef

define impl_sources
$(wildcard $(1)/*.c) $(wildcard $(1)/*.s) $(wildcard $(1)/*.S)
endef

define impl_lib_sources
$(filter %.c %.s %.S,$(COMMON_LIB_SRCS)) \
$(filter %.c %.s %.S,$(PLATFORM_LIB_SRCS)) \
$(call impl_sources,$(1))
endef

define impl_cppflags
$(if $(call dkex_sig_mldsa_impl,$(1)),-DDKEX_SIG_BACKEND_MLDSA -DDKEX_SIG_MLDSA_LEVEL=$(DKEX_SIG_MLDSA_LEVEL) -DDILITHIUM_MODE=$(DKEX_SIG_MLDSA_LEVEL))
endef

define include_flags_for_impl
-I$(CURDIR)/common \
-I$(CURDIR)/$(1) \
$(foreach dir,$(PLATFORM_INCLUDE_DIRS),-I$(CURDIR)/$(dir))
endef

define dkex_sig_mldsa_source
$(if $(call dkex_sig_mldsa_impl,$(1)),$(filter $(1)/dkex_sig_mldsa.c $(1)/randombytes.c,$(2)))
endef

define source_include_flags_for_impl
$(if $(call dkex_sig_mldsa_source,$(1),$(2)),-I$(CURDIR)/crypto_sign/dilithium/ref) $(call include_flags_for_impl,$(1))
endef

define profile_dir
$(if $(filter hashprof,$(1)),hashprof/,)
endef

define obj_from_src
obj/$(call profile_dir,$(2))$(call impl_name,$(1))/$(patsubst %.c,%.o,$(patsubst %.S,%.o,$(patsubst %.s,%.o,$(3))))
endef

define lib_objects
$(foreach src,$(call impl_lib_sources,$(1)),$(call obj_from_src,$(1),$(2),$(src)))
endef

define app_source
$(call family_of_impl,$(1))/$(2).c
endef

define app_object
$(call obj_from_src,$(1),normal,$(call app_source,$(1),$(2)))
endef

define lib_target
obj/$(call profile_dir,$(2))lib$(call impl_name,$(1)).a
endef

define mldsa_obj_from_src
obj/$(call impl_name,$(1))_mldsa/$(patsubst %.c,%.o,$(2))
endef

define mldsa_lib_objects
$(foreach src,$(DKEX_SIG_MLDSA_SRCS),$(call mldsa_obj_from_src,$(1),$(src)))
endef

define mldsa_lib_target
$(if $(call dkex_sig_mldsa_impl,$(1)),obj/lib$(call impl_name,$(1))_mldsa.a)
endef

define elf_target
elf/$(call impl_name,$(1))_$(2).elf
endef

define bin_target
bin/$(call impl_name,$(1))_$(2).bin
endef

define elf_library
$(call lib_target,$(1),$(if $(filter hashing,$(2)),hashprof,normal))
endef

define elf_libraries
$(call elf_library,$(1),$(2)) $(call mldsa_lib_target,$(1))
endef

define lib_cppflags
$(if $(filter hashprof,$(2)),-DHASHING_PROFILE)
endef

ELFS := $(foreach impl,$(IMPLS),$(foreach app,$(call selected_apps_for_impl,$(impl)),$(call elf_target,$(impl),$(app))))
BINS := $(ELFS:elf/%.elf=bin/%.bin)

define define_impl
$(call lib_target,$(1),normal): $(call lib_objects,$(1),normal)
	@printf '  AR      $$@\n'
	$(Q)mkdir -p $$(@D)
	$(Q)$(AR) rcs $$@ $$^

$(call lib_target,$(1),hashprof): $(call lib_objects,$(1),hashprof)
	@printf '  AR      $$@\n'
	$(Q)mkdir -p $$(@D)
	$(Q)$(AR) rcs $$@ $$^

$(if $(call dkex_sig_mldsa_impl,$(1)),$(eval $(call mldsa_lib_target,$(1)): $(call mldsa_lib_objects,$(1)) ; @printf '  AR      $$@\n'; $(Q)mkdir -p $$(@D); $(Q)$(AR) rcs $$@ $$^))

$(foreach src,$(DKEX_SIG_MLDSA_SRCS),$(if $(call dkex_sig_mldsa_impl,$(1)),$(eval $(call mldsa_obj_from_src,$(1),$(src)): $(src) $(COMPILEDEPS) | platform-sync ; @printf '  CC      $(src) [mldsa]\n'; $(Q)mkdir -p $$(@D); $(Q)$(CC) $(CPPFLAGS) $(call impl_cppflags,$(1)) $(CFLAGS) -I$(CURDIR)/crypto_sign/dilithium/ref -c $(src) -o $$@)))

$(foreach src,$(call impl_lib_sources,$(1)),$(eval $(call obj_from_src,$(1),normal,$(src)): $(src) $(COMPILEDEPS) | platform-sync ; @printf '  $(if $(filter %.c,$(src)),CC,AS)      $(src)\n'; $(Q)mkdir -p $$(@D); $(Q)$(CC) $(CPPFLAGS) $(call impl_cppflags,$(1)) $(CFLAGS) $(call source_include_flags_for_impl,$(1),$(src)) -c $(src) -o $$@))
$(foreach src,$(call impl_lib_sources,$(1)),$(eval $(call obj_from_src,$(1),hashprof,$(src)): $(src) $(COMPILEDEPS) | platform-sync ; @printf '  $(if $(filter %.c,$(src)),CC,AS)      $(src) [hashprof]\n'; $(Q)mkdir -p $$(@D); $(Q)$(CC) $(CPPFLAGS) $(call lib_cppflags,$(1),hashprof) $(call impl_cppflags,$(1)) $(CFLAGS) $(call source_include_flags_for_impl,$(1),$(src)) -c $(src) -o $$@))

$(foreach app,$(call selected_apps_for_impl,$(1)),$(eval $(call app_object,$(1),$(app)): $(call app_source,$(1),$(app)) $(COMPILEDEPS) | platform-sync ; @printf '  CC      $(call app_source,$(1),$(app))\n'; $(Q)mkdir -p $$(@D); $(Q)$(CC) $(CPPFLAGS) $(call impl_cppflags,$(1)) $(CFLAGS) $(call include_flags_for_impl,$(1)) -c $(call app_source,$(1),$(app)) -o $$@))

$(foreach app,$(call selected_apps_for_impl,$(1)),$(eval $(call elf_target,$(1),$(app)): $(call app_object,$(1),$(app)) $(call elf_libraries,$(1),$(app)) $(LIBDEPS) $(LDSCRIPT) | platform-sync))
$(foreach app,$(call selected_apps_for_impl,$(1)),$(eval $(call elf_target,$(1),$(app)):
	@printf '  LD      $$@\n'
	$(Q)mkdir -p $$(@D)
	$(Q)$(LD) $(CFLAGS) $(call app_object,$(1),$(app)) $(LDFLAGS) -Wl,--start-group $(call elf_libraries,$(1),$(app)) $(LDLIBS) -Wl,--end-group -o $$@
	@printf '  SIZE    $$@\n'
	$(Q)$(SIZE) $$@))

$(foreach app,$(call selected_apps_for_impl,$(1)),$(eval $(call bin_target,$(1),$(app)): $(call elf_target,$(1),$(app))
	@printf '  OBJCOPY $$@\n'
	$(Q)mkdir -p $$(@D)
	$(Q)$(OBJCOPY) -Obinary $$< $$@))

-include $(1)/config.mk
-include mk/$(call impl_name,$(1)).mk
endef

$(foreach impl,$(IMPLS),$(eval $(call define_impl,$(impl))))
