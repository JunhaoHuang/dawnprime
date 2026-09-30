
# NGCCM4

## Introduction
This repository aims to provide an automated tools, similar to [pqm4](https://github.com/mupq/pqm4) for benchmarking algorithms submitted to the New Generation Commercial Cryptography ([NGCC](https://niccs.org.cn/symmbzyjy/tzgg/pc/content/1976155884915003392/content_1976155884915003392.html)) issued by the Institute of Commercial Cryptography Standards (ICCS) in China.

--------------------
## Clone and Dependencies

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
		- SM3 for xof and drng, required by ICCS
		- SHA3 for better comparison with NIST's variants of PQC schemes.
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
  output (used by `host_unidirectional.py` and `benchmark_schemes.py`) requires
  an external USB-to-UART adapter wired to `USART2` on `PA2` (TX) / `PA3` (RX)
  at 38400 baud.

### Building and Benchmarking Scripts

The repository also provides two Python helper scripts for batch builds and benchmark collection:

- `build_schemes.py`: discovers implementations for selected schemes and builds every app available in the corresponding family directory.
- `benchmark_schemes.py`: runs the `speed`, `stack`, and `hashing` apps, captures their output, and writes benchmark summaries.

Both scripts must be run from the repository root:

```bash
cd ngccm4
```

Supported platforms are:

```text
mps2-an386
nucleo-l4r5zi
stm32f4discovery
```

Other `PLATFORM` values are rejected by the scripts.

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
python3 build_schemes.py PLATFORM=nucleo-l4r5zi {SCHEME_NAME} USE_SM3_ASM=1 USE_KECCAK=0 LTO=1 NGCC_ITERATIONS=100 -j8
```

The script searches `crypto_kem`, `crypto_kex`, and `crypto_sign`. An implementation is detected when the implementation directory contains the family entry file, for example `KEM_AlgorithmInstance.c` for KEM schemes.

#### Benchmark Runs

Run the default benchmark apps, `speed`, `stack`, and `hashing`, for all implementations of selected schemes. Omit scheme names or use `all` to benchmark every discovered scheme:

```bash
python3 benchmark_schemes.py
python3 benchmark_schemes.py all
python3 benchmark_schemes.py PLATFORM=nucleo-l4r5zi {SCHEME_NAME...} --apps speed hashing
python3 benchmark_schemes.py PLATFORM=stm32f4discovery {SCHEME_NAME...} --apps speed hashing
python3 benchmark_schemes.py PLATFORM=mps2-an386 {SCHEME_NAME...} --apps speed hashing
```

Select a subset of apps with `--apps`:

```bash
python3 benchmark_schemes.py PLATFORM=nucleo-l4r5zi {SCHEME_NAME...} --apps speed
python3 benchmark_schemes.py PLATFORM=nucleo-l4r5zi {SCHEME_NAME...} --apps speed stack hashing
```

Forward make variables after `PLATFORM=...` as usual:

```bash
python3 benchmark_schemes.py PLATFORM=nucleo-l4r5zi {SCHEME_NAME...} USE_SM3_ASM=1 USE_KECCAK=0 LTO=1 NGCC_ITERATIONS=100 -j8
```

For `mps2-an386`, the benchmark script runs each target through QEMU:

```bash
make PLATFORM=mps2-an386 <target> qemu-run
```

For `nucleo-l4r5zi`, the script builds each target, flashes it with:

```bash
openocd -f st_nucleo_l4r5.cfg -c "program <elf> verify reset exit"
```

For `stm32f4discovery`, the script builds each target and flashes it with the
OpenOCD-provided ST-Link and STM32F4 target configs:

```bash
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg -c "program <elf> verify reset exit"
```

Hardware benchmark output is captured from the serial port until the `#` completion marker is received. By default the script uses `/dev/ttyACM0` on Linux and `/dev/tty.usbserial-0001` on macOS, at 38400 baud. Override these when needed:

```bash
python3 benchmark_schemes.py PLATFORM=nucleo-l4r5zi {SCHEME_NAME...} --serial-port /dev/ttyACM1 --baud 38400
```

Benchmark outputs are written to:

```text
Out/benchmark_summary.csv
Out/benchmark_summary.md
Out/benchmark_raw/<target>.run<N>.txt
```

The CSV keeps raw metric names for post-processing. The Markdown summary is grouped by family and app. The `speed` table reports average, median, minimum, and maximum. The `stack` table reports average only. The `hashing` table reports the percentage of total operation cycles spent in hashing:

```text
average(<operation>_hash_cycles) / average(<operation>_cycles) * 100
```

Notes:

- Compare benchmark numbers only within the same platform. QEMU `mps2-an386` timings are useful for automation and regression checks, but they are not cycle-accurate hardware measurements.
- Hardware benchmark runs require `openocd`, a connected board, and a readable serial device.
- Use `--dry-run` to inspect the generated build, flash, and run commands without executing them.
- Use `--runs N` to repeat each target and aggregate samples in the summaries.


## Usage of SHA3

NGCCM4 uses SM3-based hashing and deterministic random generation by default. To build the schemes with the SHA3/SHAKE code path, pass `USE_KECCAK=1` to `make`, `build_schemes.py`, or `benchmark_schemes.py`.

When `USE_KECCAK=1` is enabled, the build system defines `USE_KECCAK` and adds the FIPS 202 implementation files from `common/`:

```text
common/fips202.c
common/fips202.h
common/keccakf1600.S
common/keccakf1600.h
common/randombytes.c
common/randombytes.h
```

This switches the guarded scheme code to the Keccak/SHA3/SHAKE implementation, including SHAKE-based XOF usage in sampling and SHA3/SHAKE-based hashing paths where the scheme code is guarded by `#ifdef USE_KECCAK`. For schemes that want to use SHA3, you need to add support for the SHA3 calls using `#ifdef USE_KECCAK` manually.

Examples:

```bash
make PLATFORM=nucleo-l4r5zi USE_KECCAK=1 crypto_kem_{SCHEME_NAME}_ref_test
make PLATFORM=mps2-an386 USE_KECCAK=1 crypto_kem_{SCHEME_NAME}_ref_test qemu-run -j1
python3 build_schemes.py PLATFORM=nucleo-l4r5zi {SCHEME_NAME...} USE_KECCAK=1
python3 benchmark_schemes.py PLATFORM=nucleo-l4r5zi {SCHEME_NAME...} --apps speed hashing USE_KECCAK=1
```

To use the default SM3 path explicitly, pass `USE_KECCAK=0`:

```bash
python3 benchmark_schemes.py PLATFORM=nucleo-l4r5zi {SCHEME_NAME} --apps speed hashing USE_KECCAK=0
```

Notes:

- `USE_KECCAK` only accepts `0` or `1`; other values are rejected by `mk/config.mk`.
- Changing `USE_KECCAK` changes the build configuration, so the make system will clean stale `bin`, `elf`, and `obj` outputs automatically.
- `USE_SM3_ASM=1` controls the optimized SM3 assembly path. It is independent from `USE_KECCAK`.


## LICENSES
Different parts of **ngccm4** have different licenses. 
Each subdirectory containing implementations contains a LICENSE or COPYING file stating 
under what license that specific implementation is released. 
The files in common contain licensing information at the top of the file. 

All other code in this repository is licensed under [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) and under the conditions of [CC0](https://creativecommons.org/publicdomain/zero/1.0/).

