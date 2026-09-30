#!/usr/bin/env python3
"""Generate the shared loop-free Cortex-M4 radix-16 R2 multipliers."""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import tempfile
from pathlib import Path


LANE_MASK = 0x11111111

class Asm:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, line: str = "") -> None:
        self.lines.append(line)

    def extend(self, lines: list[str]) -> None:
        self.lines.extend(lines)

    def function(self, name: str, *, public: bool) -> None:
        self.add(".align 2")
        self.add(".thumb_func")
        if public:
            self.add(f".global {name}")
        self.add(f".type {name}, %function")
        self.add(f"{name}:")

    def end_function(self, name: str) -> None:
        self.add(f".size {name}, .-{name}")
        self.add()

    def render(self) -> str:
        return "\n".join(self.lines) + "\n"


def mem(reg: str, byte_offset: int) -> str:
    if byte_offset == 0:
        return f"[{reg}]"
    return f"[{reg}, #{byte_offset}]"


def load(asm: Asm, dst: str, base: str, word: int) -> None:
    asm.add(f"    ldr.w {dst}, {mem(base, 4 * word)}")


def store(asm: Asm, src: str, base: str, word: int) -> None:
    asm.add(f"    str.w {src}, {mem(base, 4 * word)}")


def load_pair(
    asm: Asm, dst0: str, dst1: str, base: str, word: int
) -> None:
    asm.add(f"    ldrd {dst0}, {dst1}, {mem(base, 4 * word)}")


def store_pair(
    asm: Asm, src0: str, src1: str, base: str, word: int
) -> None:
    asm.add(f"    strd {src0}, {src1}, {mem(base, 4 * word)}")


def add_pointer(asm: Asm, dst: str, base: str, byte_offset: int) -> None:
    if byte_offset == 0:
        asm.add(f"    mov {dst}, {base}")
    else:
        asm.add(f"    add.w {dst}, {base}, #{byte_offset}")


def emit_xor2_block(
    asm: Asm,
    *,
    words: int,
    dst_reg: str,
    dst_word: int,
    left_reg: str,
    left_word: int,
    right_reg: str,
    right_word: int,
) -> None:
    """XOR two even-sized word ranges using grouped doubleword transfers."""
    assert words % 2 == 0
    for i in range(0, words, 2):
        load_pair(asm, "r0", "r1", left_reg, left_word + i)
        load_pair(asm, "r2", "r3", right_reg, right_word + i)
        asm.add("    eor.w r0, r0, r2")
        asm.add("    eor.w r1, r1, r3")
        store_pair(asm, "r0", "r1", dst_reg, dst_word + i)


def emit_xor3_block(
    asm: Asm,
    *,
    words: int,
    dst_reg: str,
    dst_word: int,
    first_reg: str,
    first_word: int,
    second_reg: str,
    second_word: int,
    third_reg: str,
    third_word: int,
) -> None:
    """XOR three even-sized word ranges using four caller-saved registers."""
    assert words % 2 == 0
    for i in range(0, words, 2):
        load_pair(asm, "r0", "r1", first_reg, first_word + i)
        load_pair(asm, "r2", "r3", second_reg, second_word + i)
        asm.add("    eor.w r0, r0, r2")
        asm.add("    eor.w r1, r1, r3")
        load_pair(asm, "r2", "r3", third_reg, third_word + i)
        asm.add("    eor.w r0, r0, r2")
        asm.add("    eor.w r1, r1, r3")
        store_pair(asm, "r0", "r1", dst_reg, dst_word + i)


def emit_product_scan(
    asm: Asm,
    *,
    words: int,
    out_reg: str,
    a_reg: str,
    b_reg: str,
    mask_reg: str,
    cyclic: bool,
    a_words: tuple[str, ...] | None = None,
    b_words: tuple[str, ...] | None = None,
) -> None:
    """Emit a full word-product scan with parity reduction after every UMLAL."""
    asm.add("    movs r3, #0")
    for k in range(2 * words):
        asm.add("    mov r2, r3")
        asm.add("    movs r3, #0")
        lo = max(0, k - (words - 1))
        hi = min(words - 1, k)
        for i in range(lo, hi + 1):
            j = k - i
            lhs = a_words[i] if a_words is not None else "r0"
            rhs = b_words[j] if b_words is not None else "r1"
            if a_words is None:
                load(asm, lhs, a_reg, i)
            if b_words is None:
                load(asm, rhs, b_reg, j)
            asm.add(f"    umlal r2, r3, {lhs}, {rhs}")
            if mask_reg:
                asm.add(f"    and.w r2, r2, {mask_reg}")
                asm.add(f"    and.w r3, r3, {mask_reg}")
            else:
                asm.add(f"    and.w r2, r2, #{LANE_MASK:#010x}")
                asm.add(f"    and.w r3, r3, #{LANE_MASK:#010x}")
        if cyclic and k >= words:
            load(asm, "r1", out_reg, k - words)
            asm.add("    eor.w r2, r2, r1")
            store(asm, "r2", out_reg, k - words)
        else:
            store(asm, "r2", out_reg, k)


def emit_tiny_cyclic(asm: Asm, degree: int) -> None:
    name = f"r2_radix16_mul_{degree}_asm"
    asm.function(name, public=True)
    asm.add("    ldr.w r3, [r1]")
    asm.add("    ldr.w r12, [r2]")
    if degree == 2:
        asm.add("    movs r1, #0x11")
        asm.add("    smulbb r3, r3, r12")
        asm.add("    eor.w r3, r3, r3, lsr #8")
    else:
        asm.add("    movw r1, #0x1111")
        asm.add("    smulbb r3, r3, r12")
        asm.add("    eor.w r3, r3, r3, lsr #16")
    asm.add("    and.w r1, r1, r3")
    asm.add("    str.w r1, [r0]")
    asm.add("    bx lr")
    asm.end_function(name)


def emit_direct_cyclic(asm: Asm, degree: int) -> None:
    words = degree // 8
    name = f"r2_radix16_mul_{degree}_asm"
    asm.function(name, public=True)

    if words == 1:
        asm.add("    ldr.w r3, [r1]")
        asm.add("    ldr.w r12, [r2]")
        asm.add("    umull r1, r2, r3, r12")
        asm.add("    eor.w r1, r1, r2")
        asm.add(f"    and.w r1, r1, #{LANE_MASK:#010x}")
        asm.add("    str.w r1, [r0]")
        asm.add("    bx lr")
        asm.end_function(name)
        return

    if words == 2:
        asm.add("    push {r4-r7}")
        load_pair(asm, "r4", "r5", "r1", 0)
        load_pair(asm, "r6", "r7", "r2", 0)
        a_words = ("r4", "r5")
        b_words = ("r6", "r7")
        saved = "r4-r7"
        b_reg = "r2"
    elif words == 4:
        asm.add("    push {r4-r11}")
        asm.add("    ldm.w r1, {r4-r7}")
        asm.add("    ldm.w r2, {r8-r11}")
        a_words = ("r4", "r5", "r6", "r7")
        b_words = ("r8", "r9", "r10", "r11")
        saved = "r4-r11"
        b_reg = "r2"
    else:
        assert words == 8
        asm.add("    push {r4-r11}")
        asm.add("    mov r12, r2")
        asm.add("    ldm.w r1, {r4-r11}")
        a_words = tuple(f"r{i}" for i in range(4, 12))
        b_words = None
        saved = "r4-r11"
        b_reg = "r12"

    emit_product_scan(
        asm,
        words=words,
        out_reg="r0",
        a_reg="r1",
        b_reg=b_reg,
        mask_reg="",
        cyclic=True,
        a_words=a_words,
        b_words=b_words,
    )
    asm.add(f"    pop {{{saved}}}")
    asm.add("    bx lr")
    asm.end_function(name)


def emit_linear_leaf(asm: Asm) -> None:
    name = "r2_radix16_linear_mul4_asm"
    asm.function(name, public=False)
    asm.add("    push {r4-r11}")
    asm.add("    ldm.w r1, {r4-r7}")
    asm.add("    ldm.w r2, {r8-r11}")
    emit_product_scan(
        asm,
        words=4,
        out_reg="r0",
        a_reg="r1",
        b_reg="r2",
        mask_reg="",
        cyclic=False,
        a_words=("r4", "r5", "r6", "r7"),
        b_words=("r8", "r9", "r10", "r11"),
    )
    asm.add("    pop {r4-r11}")
    asm.add("    bx lr")
    asm.end_function(name)


def emit_sum_block(asm: Asm, words: int) -> None:
    emit_xor2_block(
        asm,
        words=words,
        dst_reg="r8",
        dst_word=0,
        left_reg="r5",
        left_word=0,
        right_reg="r5",
        right_word=words,
    )
    emit_xor2_block(
        asm,
        words=words,
        dst_reg="r9",
        dst_word=0,
        left_reg="r6",
        left_word=0,
        right_reg="r6",
        right_word=words,
    )


def emit_linear_karatsuba(asm: Asm, words: int) -> None:
    half = words // 2
    child = f"r2_radix16_linear_mul{half}_asm"
    name = f"r2_radix16_linear_mul{words}_asm"
    local_bytes = 8 * words

    asm.function(name, public=False)
    asm.add("    push.w {r3-r9, lr}")
    asm.add(f"    sub.w sp, sp, #{local_bytes}")
    asm.add("    mov r4, r0")
    asm.add("    mov r5, r1")
    asm.add("    mov r6, r2")
    asm.add("    mov r7, sp")
    add_pointer(asm, "r8", "sp", 4 * words)
    add_pointer(asm, "r9", "sp", 6 * words)
    asm.add()

    asm.add("    mov r0, r4")
    asm.add("    mov r1, r5")
    asm.add("    mov r2, r6")
    asm.add(f"    bl {child}")
    add_pointer(asm, "r0", "r4", 4 * words)
    add_pointer(asm, "r1", "r5", 4 * half)
    add_pointer(asm, "r2", "r6", 4 * half)
    asm.add(f"    bl {child}")
    asm.add()

    emit_sum_block(asm, half)
    asm.add()
    asm.add("    mov r0, r7")
    asm.add("    mov r1, r8")
    asm.add("    mov r2, r9")
    asm.add(f"    bl {child}")
    asm.add()

    emit_xor3_block(
        asm,
        words=words,
        dst_reg="r7",
        dst_word=0,
        first_reg="r7",
        first_word=0,
        second_reg="r4",
        second_word=0,
        third_reg="r4",
        third_word=words,
    )
    asm.add()
    emit_xor2_block(
        asm,
        words=words,
        dst_reg="r4",
        dst_word=half,
        left_reg="r4",
        left_word=half,
        right_reg="r7",
        right_word=0,
    )

    asm.add(f"    add.w sp, sp, #{local_bytes}")
    asm.add("    pop.w {r3-r9, pc}")
    asm.end_function(name)


def emit_cyclic_karatsuba(asm: Asm, degree: int) -> None:
    words = degree // 8
    half = words // 2
    child = f"r2_radix16_linear_mul{half}_asm"
    name = f"r2_radix16_mul_{degree}_asm"
    local_bytes = 8 * words

    asm.function(name, public=True)
    asm.add("    push.w {r3-r9, lr}")
    asm.add(f"    sub.w sp, sp, #{local_bytes}")
    asm.add("    mov r4, r0")
    asm.add("    mov r5, r1")
    asm.add("    mov r6, r2")
    asm.add("    mov r7, sp")
    add_pointer(asm, "r8", "sp", 4 * words)
    add_pointer(asm, "r9", "sp", 6 * words)
    asm.add()

    asm.add("    mov r0, r4")
    asm.add("    mov r1, r5")
    asm.add("    mov r2, r6")
    asm.add(f"    bl {child}")
    asm.add("    mov r0, r7")
    add_pointer(asm, "r1", "r5", 4 * half)
    add_pointer(asm, "r2", "r6", 4 * half)
    asm.add(f"    bl {child}")
    asm.add()

    emit_xor2_block(
        asm,
        words=words,
        dst_reg="r4",
        dst_word=0,
        left_reg="r4",
        left_word=0,
        right_reg="r7",
        right_word=0,
    )
    asm.add()
    emit_sum_block(asm, half)
    asm.add()
    asm.add("    mov r0, r7")
    asm.add("    mov r1, r8")
    asm.add("    mov r2, r9")
    asm.add(f"    bl {child}")
    asm.add()

    emit_xor2_block(
        asm,
        words=words,
        dst_reg="r7",
        dst_word=0,
        left_reg="r7",
        left_word=0,
        right_reg="r4",
        right_word=0,
    )
    asm.add()
    emit_xor2_block(
        asm,
        words=half,
        dst_reg="r4",
        dst_word=half,
        left_reg="r4",
        left_word=half,
        right_reg="r7",
        right_word=0,
    )
    emit_xor2_block(
        asm,
        words=half,
        dst_reg="r4",
        dst_word=0,
        left_reg="r4",
        left_word=0,
        right_reg="r7",
        right_word=half,
    )

    asm.add(f"    add.w sp, sp, #{local_bytes}")
    asm.add("    pop.w {r3-r9, pc}")
    asm.end_function(name)


def emit_rectangular(asm: Asm, long_degree: int, short_degree: int) -> None:
    words = long_degree // 8
    half = short_degree // 8
    assert words == 2 * half
    child = f"r2_radix16_linear_mul{half}_asm"
    name = f"r2_radix16_mul_{long_degree}x{short_degree}_asm"
    local_bytes = 8 * words

    asm.function(name, public=True)
    asm.add("    push.w {r3-r9, lr}")
    asm.add(f"    sub.w sp, sp, #{local_bytes}")
    asm.add("    mov r4, r0")
    asm.add("    mov r5, r1")
    asm.add("    mov r6, r2")
    asm.add("    mov r7, sp")
    add_pointer(asm, "r8", "sp", 4 * words)
    asm.add()

    asm.add("    mov r0, r7")
    asm.add("    mov r1, r5")
    asm.add("    mov r2, r6")
    asm.add(f"    bl {child}")
    asm.add("    mov r0, r8")
    add_pointer(asm, "r1", "r5", 4 * half)
    asm.add("    mov r2, r6")
    asm.add(f"    bl {child}")
    asm.add()

    emit_xor2_block(
        asm,
        words=half,
        dst_reg="r4",
        dst_word=0,
        left_reg="r7",
        left_word=0,
        right_reg="r8",
        right_word=half,
    )
    emit_xor2_block(
        asm,
        words=half,
        dst_reg="r4",
        dst_word=half,
        left_reg="r7",
        left_word=half,
        right_reg="r8",
        right_word=0,
    )

    asm.add(f"    add.w sp, sp, #{local_bytes}")
    asm.add("    pop.w {r3-r9, pc}")
    asm.end_function(name)


def generate() -> str:
    asm = Asm()
    asm.extend(
        [
            "/*",
            " * Generated by crypto_kem/common/gen_r2_radix16_mul.py.",
            " * Do not edit this file by hand.",
            " *",
            " * Inputs and outputs use eight GF(2) coefficients per uint32_t at",
            " * bit positions 0,4,...,28.  Every UMLAL masks both 32-bit halves",
            " * immediately with 0x11111111, preventing radix-lane carries.",
            " * Hot leaves preload complete operands and Karatsuba glue batches",
            " * adjacent words with LDRD/STRD to reduce load/store issue cost.",
            " * Public cyclic kernels require non-overlapping output and inputs.",
            " */",
            "",
            ".syntax unified",
            ".cpu cortex-m4",
            ".thumb",
            "",
        ]
    )

    emit_tiny_cyclic(asm, 2)
    emit_tiny_cyclic(asm, 4)
    for degree in (8, 16, 32, 64):
        emit_direct_cyclic(asm, degree)
    for degree in (128, 256, 512):
        emit_cyclic_karatsuba(asm, degree)
    emit_rectangular(asm, 256, 128)
    emit_rectangular(asm, 512, 256)
    emit_linear_leaf(asm)
    for words in (8, 16, 32):
        emit_linear_karatsuba(asm, words)
    return asm.render()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    default_output = script_dir / "r2_radix16_mul_generated.inc"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=default_output)
    parser.add_argument(
        "--check",
        action="store_true",
        help="regenerate into a temporary file and compare byte-for-byte",
    )
    args = parser.parse_args()

    data = generate().encode("ascii")
    if args.check:
        if not args.output.is_file():
            parser.error(f"checked-in output does not exist: {args.output}")
        with tempfile.NamedTemporaryFile(prefix="r2-radix16-", suffix=".inc") as tmp:
            tmp.write(data)
            tmp.flush()
            if not filecmp.cmp(tmp.name, args.output, shallow=False):
                parser.error(f"generated output differs from {args.output}")
        print(f"OK {sha256(data)}  {args.output}")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(f"{sha256(data)}  {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
