
# DAWN$^\prime$: Improved DAWN and Accelerated Implementation on ARM Cortex-M4

## Introduction
This repository aims to provide DAWN$^\prime$, an improved DAWN and accelerated implementation on ARM Cortex-M4.

--------------------
## Clone and Dependencies

```base
# Clone this repository recursively by
git clone --recursive https://github.com/JunhaoHuang/dawnprime.git
```

This repository relies on [libopencm3(@87a080c)](https://github.com/libopencm3/libopencm3/tree/87a080c94ce67643216464821c752c1c406c6414) to provide M4-related supports.

## Set-up/Installation

The makefile system requires a few host tools to be installed:

- `make`
- `python3`
- `arm-none-eabi-gcc`, `arm-none-eabi-cpp`, `arm-none-eabi-objcopy`, `arm-none-eabi-size`
- `qemu-system-arm` for `PLATFORM=mps2-an386` and `qemu-run`
- `openocd` only if you want to flash and debug on real hardware

On Ubuntu/Debian, install them with the executable helper:

```bash
./install-deps-ubuntu.sh
```

If you do not need hardware flashing, omit `openocd`:

```bash
./install-deps-ubuntu.sh --no-openocd
```

Tool purpose:

- `gcc-arm-none-eabi` and `binutils-arm-none-eabi` provide the Cortex-M4 cross compiler and binary utilities used by the makefiles.
- `python3` is needed by `libopencm3/scripts/genlink.py` during linker-script and device setup.
- `qemu-system-arm` is required only for QEMU-based runs on `mps2-an386`.
- `openocd` is optional and is only needed for flashing supported STM32 boards.

Quick verification:

```bash
arm-none-eabi-gcc --version
python3 --version
qemu-system-arm --version
openocd --version
```

If you do not need hardware flashing, `openocd` can be omitted.


## Structure
- ngccm4:
	- common: common files for the algorithms
		- SHA3-256 / SHAKE256 (FIPS 202) for hashing and XOF, `randombytes` for seeds
	- crypto_kem: Key Encapsulation Mechanism schemes
		- DKE
		- ZEN: NTRU-based KEM
	- crypto_sign: Digital Signature schemes
	- crypto_kex: Key Exchange schemes
	- libopencm3: third-party library for ARM Cortex-M4
	- mk: Makefiles related for building and compiling
	- README.md

## Manual Usage

The preferred interface is the pqm4-style output-stem target. You can build a binary directly by naming the expected output stem:

```bash
make crypto_kem_{SCHEME_NAME}_ref_test
make crypto_kem_{SCHEME_NAME}_ref_speed
make crypto_kem_{SCHEME_NAME}_ref_hashing
```

The generated files are:

```bash
elf/crypto_kem_{SCHEME_NAME}_ref_test.elf
bin/crypto_kem_{SCHEME_NAME}_ref_test.bin
```

The explicit selector form is still supported when needed:

```bash
make FAMILY=crypto_kem SCHEME={SCHEME_NAME} IMPLEMENTATION=ref APP=test -j1
```

## Usage for QEMU Emulation

Typical build/run examples:

```bash
make PLATFORM=mps2-an386 crypto_kem_{SCHEME_NAME}_ref_test qemu-run -j1
```


Notes:
- The QEMU build and run should be only used for correctness verification, e.g., test, testvectors. 
- Supported families in the makefile system are `crypto_kem`, `crypto_kex`, and `crypto_sign`.
- The current repository contains KEM implementations. `crypto_kex` and `crypto_sign` are already wired into the discovery/build system
- Supported hardware platforms are `nucleo-l4r5zi` (STM32L4R5ZI) and `stm32f4discovery` (STM32F407VG); `mps2-an386` is the QEMU emulation target.
- `PLATFORM=nucleo-l4r5zi` is the default hardware build target. Pass `PLATFORM=stm32f4discovery` to build for the STM32F4DISCOVERY board.
- `-j1` means serial build mode. You can increase it, for example `-j4`, once the environment is working.

## Flashing on Real Hardware

The makefile system currently builds `.elf` and `.bin` files but does not provide a dedicated `flash` target. Use `openocd` to program the generated `.elf` file to hardware.

### Default platform: `nucleo-l4r5zi`

Build an application first:

```bash
make crypto_kem_{SCHEME_NAME}_ref_test
```

This generates:

```bash
elf/crypto_kem_{SCHEME_NAME}_ref_test.elf
bin/crypto_kem_{SCHEME_NAME}_ref_test.bin
```

Flash it with the project-local OpenOCD config:

```bash
openocd \
	-f st_nucleo_l4r5.cfg \
	-c "program elf/crypto_kem_{SCHEME_NAME}_ref_test.elf verify reset exit"
```

To receive the output, run `python3 hostside/host_unidirectional.py`.

Notes:

- `nucleo-l4r5zi` is the default `PLATFORM`, so you do not need to pass `PLATFORM=nucleo-l4r5zi`.
- This expects the board to be connected through the on-board ST-Link debugger.

### Platform: `stm32f4discovery`

Build an application for the STM32F4DISCOVERY (STM32F407VG) board:

```bash
make PLATFORM=stm32f4discovery crypto_kem_{SCHEME_NAME}_ref_test
```

This generates:

```bash
elf/crypto_kem_{SCHEME_NAME}_ref_test.elf
bin/crypto_kem_{SCHEME_NAME}_ref_test.bin
```

Flash it with OpenOCD using the ST-Link interface and the STM32F4 target config:

```bash
openocd \
	-f interface/stlink.cfg \
	-f target/stm32f4x.cfg \
	-c "program elf/crypto_kem_{SCHEME_NAME}_ref_test.elf verify reset exit"
```

These two config files ship with OpenOCD itself (no project-local `.cfg` is
needed for this board). To flash the raw `.bin` instead, give the flash base
address:

```bash
openocd \
	-f interface/stlink.cfg \
	-f target/stm32f4x.cfg \
	-c "program bin/crypto_kem_{SCHEME_NAME}_ref_test.bin 0x08000000 verify reset exit"
```

Notes:

- This expects the board to be connected through the on-board ST-Link debugger
  (the mini-USB / ST-Link port).
- If OpenOCD reports a USB permission error, install the ST-Link udev rules
  (`contrib/60-openocd.rules` from the OpenOCD distribution) or run the command
  with `sudo`.
- The STM32F4DISCOVERY's on-board ST-Link has no virtual COM port, so serial
  output (used by `host_unidirectional.py`) requires
  an external USB-to-UART adapter wired to `USART2` on `PA2` (TX) / `PA3` (RX)
  at 38400 baud.

### Build Script

The repository provides a Python helper script for batch builds:

- `build_schemes.py`: discovers implementations for selected schemes and builds every app available in the corresponding family directory.

The script must be run from the repository root:

```bash
cd dawnprime
```

Supported platforms are:

```text
mps2-an386
nucleo-l4r5zi
stm32f4discovery
```

Other `PLATFORM` values are rejected by the script.

#### Batch Builds

Build every implementation and every family app for one or more schemes. Omit scheme names or use `all` to build every discovered scheme:

```bash
python3 build_schemes.py
python3 build_schemes.py all
python3 build_schemes.py PLATFORM=nucleo-l4r5zi {SCHEME_NAME...}
python3 build_schemes.py PLATFORM=stm32f4discovery {SCHEME_NAME...}
python3 build_schemes.py PLATFORM=mps2-an386 {SCHEME_NAME...}
```

Useful build options:

```bash
python3 build_schemes.py PLATFORM=nucleo-l4r5zi {SCHEME_NAME} LTO=1 NGCC_ITERATIONS=100 -j8
```

The script searches `crypto_kem`, `crypto_kex`, and `crypto_sign`. An implementation is detected when the implementation directory contains the family entry file, for example `KEM_AlgorithmInstance.c` for KEM schemes.

## Symmetric Primitives

All implementations use Keccak-based primitives from `common/`:

```text
common/fips202.c        SHA3-256 (hashing) and SHAKE256 (XOF / seed expansion)
common/keccakf1600.S    Keccak-f[1600] permutation for ARMv7-M
common/randombytes.c    Randomness source (hardware RNG on STM32 boards, deterministic fallback on QEMU)
```

The SM3-based auxiliary functions and DRNG from the original NGCC template are not part of this repository.

Benchmark apps (`speed`, `stack`, `hashing`, `polyr2_speed`, `polyrq_speed`) can be run manually, for example:

```bash
make PLATFORM=mps2-an386 crypto_kem_DAWN_Prime_128_m4_speed qemu-run -j1
make PLATFORM=nucleo-l4r5zi crypto_kem_DAWN_Prime_128_m4_speed
openocd -f st_nucleo_l4r5.cfg -c "program elf/crypto_kem_DAWN_Prime_128_m4_speed.elf verify reset exit"
python3 hostside/host_unidirectional.py
```

The `hashing` app reports the cycles spent inside SHA3/SHAKE calls per operation.


## LICENSES
Different parts of this repository have different licenses. 
Each subdirectory containing implementations contains a LICENSE or COPYING file stating 
under what license that specific implementation is released. 
The files in common contain licensing information at the top of the file. 

All other code in this repository is licensed under [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) and under the conditions of [CC0](https://creativecommons.org/publicdomain/zero/1.0/).

