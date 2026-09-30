# Shared Cortex-M4 radix-16 R2 multiplication

`gen_r2_radix16_mul.py` deterministically generates the loop-free multiplication
include used by ZEN-128, ZEN-256, DAWN_Prime_128, and DAWN_Prime_256.  The code
was derived independently from the local scalar ring operation; no assembly was
copied from the unlicensed upstream R3 repository.

## Arithmetic contract

Each `uint32_t` stores eight GF(2) coefficients in bits 0, 4, ..., 28.  Inputs
must be canonical and the output never sets bits outside `0x11111111`.  Public
cyclic multiplication computes in GF(2)[x]/(x^n + 1), which is cyclic in
characteristic two.  Output and input buffers retain the pre-existing
non-aliasing contract.
Grouped `LDRD`/`STRD` accesses assume the 32-bit alignment provided by the
`uint32_t` API and the AAPCS-aligned stack workspaces.

Degrees 2 and 4 use packed single-word specializations.  Degrees 8 through 64
use direct, straight-line cyclic product scans.  Degrees 128 through 512 use a
fixed Karatsuba call graph terminating in a fully unrolled four-word linear
leaf.  The rectangular 256x128 and 512x256 functions use two linear products
and a single straight-line cyclic recombination.  After every UMLAL, both
32-bit halves are immediately masked; delaying this reduction could permit a
carry between radix-16 lanes.

The 16- and 32-coefficient kernels and four-word leaf preload both operands;
the 64-coefficient kernel preloads one full operand.  Karatsuba sums and
recombinations use two-word `LDRD`/`STRD` batches.

## Reproduction

From the ngccm4 repository root:

```sh
python3 crypto_kem/common/gen_r2_radix16_mul.py
python3 crypto_kem/common/gen_r2_radix16_mul.py --check
make r2-generated-check
```

Checked-in output SHA-256:

```
c22fab63425a6b4ea97f7cfcb42b6103a04375e31e2569d7788861b46b544bf1
```

The `--check` operation regenerates into a temporary file and compares it
byte-for-byte with `r2_radix16_mul_generated.inc`.

## Stack audit

The figures include all saved registers, local workspaces, and the deepest
nested leaf call.

| entry point | peak bytes | ceiling |
|---|---:|---:|
| degree 128 | 288 | 288 |
| degree 256 | 576 | 576 |
| 256x128 | 576 | 576 |
| degree 512 | 1,120 | 1,120 |
| 512x256 | 1,120 | 1,120 |

The call frames are 32 bytes for each Karatsuba level and 32 bytes for the
leaf.  Local storage is 8 bytes per input word at each Karatsuba or rectangular
level.

## Verification scope

`verify_r2_radix16.py` checks deterministic regeneration, public symbols,
absence of conditional branches in generated kernels, immediate two-half masking
after every `UMLAL`, include wiring, and stack ceilings.  The
`crypto_kem/test.c` and `crypto_kem/testvectors.c` apps provide end-to-end and
reference-output checks for each DAWN parameter set.

Arithmetic validation should also compare every degree through 512 against a
scalar GF(2) product using zero, all-one/maximum-carry, singleton, alternating,
and randomized canonical inputs.  `crypto_kem/polyr2_speed.c` supplies the
initialized, checksum-consumed timing path.  QEMU results are regression data
only; final cycle acceptance requires Cortex-M4 DWT measurements with warm-up
on hardware.
