DEVICE := stm32l4r5zi
OPENCM3_TARGET := lib/stm32/l4
DEVICES_DATA := ldscripts/devices.data
PLATFORM_LIB_SRCS := common/hal-stm32f4.c

include mk/opencm3.mk
