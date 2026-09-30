#!/usr/bin/env python3
"""Summarize per-operation cycle counts from captured benchmark logs.

Understands the output of the speed and hashing apps, where every operation is
reported as

    <operation> cycles:
    <value>

and, for the hashing app, additionally

    <operation> hash cycles:
    <value>

which is the time spent inside the Keccak primitives (SHA3-256 / SHAKE256).
When hash cycles are present the summary also prints their share of the
operation.

Examples:
    python3 average.py                                   # Out/speed_*.txt and Out/benchmark_raw/*_speed.run*.txt
    python3 average.py "Out/benchmark_raw/*_hashing.run*.txt"
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


OPERATIONS = ("keypair", "encaps", "decaps")
LINE_RE = re.compile(r"^(?P<op>keypair|encaps|decaps)\s+(?P<hash>hash\s+)?cycles:\s*$")
KERNEL_LOG_RE = re.compile(r"_(polyrq|polyr2)_speed\.run[0-9]+\.txt$")
DEFAULT_PATTERNS = (
    "Out/speed_*.txt",
    "Out/benchmark_raw/*_speed.run*.txt",
    "Out/benchmark_raw/*_hashing.run*.txt",
)


def parse_speed_file(path: Path) -> dict[str, list[int]]:
    """Return samples keyed by operation ("keypair") or hash metric ("keypair hash")."""
    results: dict[str, list[int]] = {op: [] for op in OPERATIONS}

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    while i < len(lines):
        match = LINE_RE.match(lines[i].strip())
        if not match:
            i += 1
            continue

        key = match.group("op") + (" hash" if match.group("hash") else "")
        if i + 1 >= len(lines):
            raise ValueError(f"{path}: missing cycle count after line {i + 1}")

        value_line = lines[i + 1].strip()
        try:
            value = int(value_line)
        except ValueError as exc:
            raise ValueError(
                f"{path}: invalid cycle count '{value_line}' after line {i + 1}"
            ) from exc

        results.setdefault(key, []).append(value)
        i += 2

    return results


def summarize(values: list[int]) -> tuple[int, float, int, int] | None:
    if not values:
        return None
    total = sum(values)
    count = len(values)
    return count, total / count, min(values), max(values)


def print_summary(path: Path, stats: dict[str, list[int]]) -> None:
    print(path.as_posix())
    for op in OPERATIONS:
        summary = summarize(stats.get(op, []))
        if summary is None:
            print(f"  {op:7s} count=0")
            continue
        count, avg, min_v, max_v = summary
        line = (
            f"  {op:7s} count={count:<4d} "
            f"avg={avg:10.2f} min={min_v:10d} max={max_v:10d}"
        )
        hash_summary = summarize(stats.get(f"{op} hash", []))
        if hash_summary is not None and avg > 0:
            _, hash_avg, _, _ = hash_summary
            line += f"  hash={hash_avg:10.2f} ({100.0 * hash_avg / avg:5.1f}%)"
        print(line)
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize keypair/encaps/decaps cycle counts (and Keccak hash cycles) in benchmark logs."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or glob patterns to summarize. Defaults to " + ", ".join(DEFAULT_PATTERNS) + ".",
    )
    return parser


def resolve_paths(patterns: list[str]) -> list[Path]:
    use_defaults = not patterns
    if use_defaults:
        patterns = list(DEFAULT_PATTERNS)

    resolved: list[Path] = []
    for pattern in patterns:
        matches = sorted(Path(".").glob(pattern))
        if use_defaults:
            # The polynomial kernel apps share the "_speed" suffix but report
            # no keypair/encaps/decaps operations.
            matches = [path for path in matches if not KERNEL_LOG_RE.search(path.name)]
        if matches:
            resolved.extend(matches)
            continue

        candidate = Path(pattern)
        if candidate.is_file():
            resolved.append(candidate)

    unique_paths: list[Path] = []
    seen: set[Path] = set()
    for path in resolved:
        if path not in seen:
            seen.add(path)
            unique_paths.append(path)
    return unique_paths


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    paths = resolve_paths(args.paths)

    if not paths:
        parser.error("no matching files found")

    for path in paths:
        stats = parse_speed_file(path)
        print_summary(path, stats)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
