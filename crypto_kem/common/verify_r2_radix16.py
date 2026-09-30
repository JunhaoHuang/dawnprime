#!/usr/bin/env python3
"""Reproducibility and structural checks for the generated radix-16 R2 kernels."""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON = Path(__file__).resolve().parent
GENERATOR = COMMON / "gen_r2_radix16_mul.py"
GENERATED = COMMON / "r2_radix16_mul_generated.inc"
SCHEMES = ("ZEN-128", "ZEN-256", "DAWN_Prime_128", "DAWN_Prime_256")
PUBLIC = tuple(f"r2_radix16_mul_{n}_asm" for n in (2, 4, 8, 16, 32, 64, 128, 256, 512)) + (
    "r2_radix16_mul_256x128_asm",
    "r2_radix16_mul_512x256_asm",
)
STACK_BYTES = {
    "r2_radix16_mul_128_asm": 288,
    "r2_radix16_mul_256_asm": 576,
    "r2_radix16_mul_256x128_asm": 576,
    "r2_radix16_mul_512_asm": 1120,
    "r2_radix16_mul_512x256_asm": 1120,
}
STACK_CEILINGS = {
    "r2_radix16_mul_128_asm": 288,
    "r2_radix16_mul_256_asm": 576,
    "r2_radix16_mul_256x128_asm": 576,
    "r2_radix16_mul_512_asm": 1120,
    "r2_radix16_mul_512x256_asm": 1120,
}


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def main() -> int:
    subprocess.run([sys.executable, str(GENERATOR), "--check"], check=True)
    text = GENERATED.read_text(encoding="ascii")
    lines = text.splitlines()

    if "r2_radix16_mul_words_asm" in text:
        fail("runtime word multiplier is present")
    for symbol in PUBLIC:
        if text.count(f"{symbol}:") != 1:
            fail(f"expected exactly one definition of {symbol}")
    conditional = re.compile(r"^\\s*b(?:eq|ne|cs|cc|mi|pl|vs|vc|hi|ls|ge|lt|gt|le)\\b", re.I)
    for lineno, line in enumerate(lines, 1):
        if conditional.search(line):
            fail(f"conditional branch at generated line {lineno}: {line.strip()}")
    for index, line in enumerate(lines):
        if re.search(r"\\bumlal\\b", line, re.I):
            following = [item.strip() for item in lines[index + 1:index + 3]]
            if following != [
                "and.w r2, r2, #0x11111111",
                "and.w r3, r3, #0x11111111",
            ]:
                fail(f"UMLAL at line {index + 1} lacks immediate two-half masking")
    for symbol, used in STACK_BYTES.items():
        if used > STACK_CEILINGS[symbol]:
            fail(f"stack bound exceeded for {symbol}: {used}")
    include = '#include "../../common/r2_radix16_mul_generated.inc"'
    for scheme in SCHEMES:
        wrapper = ROOT / "crypto_kem" / scheme / "m4" / "fast_radix16_r2.S"
        wrapper_text = wrapper.read_text()
        if wrapper_text.count(include) != 1:
            fail(f"{scheme} does not include the shared kernels exactly once")
        if "r2_radix16_mul_words_asm" in wrapper_text:
            fail(f"{scheme} retains the runtime word multiplier")
    digest = hashlib.sha256(GENERATED.read_bytes()).hexdigest()
    print(f"OK sha256={digest}")
    for symbol, used in STACK_BYTES.items():
        print(f"OK stack {symbol}={used} <= {STACK_CEILINGS[symbol]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
