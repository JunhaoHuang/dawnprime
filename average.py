#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


LINE_RE = re.compile(r"^(keypair|encaps|decaps)\s+cycles:\s*$")


def parse_speed_file(path: Path) -> dict[str, list[int]]:
    results: dict[str, list[int]] = {
        "keypair": [],
        "encaps": [],
        "decaps": [],
    }

    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        match = LINE_RE.match(lines[i].strip())
        if not match:
            i += 1
            continue

        op = match.group(1)
        if i + 1 >= len(lines):
            raise ValueError(f"{path}: missing cycle count after line {i + 1}")

        value_line = lines[i + 1].strip()
        try:
            value = int(value_line)
        except ValueError as exc:
            raise ValueError(
                f"{path}: invalid cycle count '{value_line}' after line {i + 1}"
            ) from exc

        results[op].append(value)
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
    for op in ("keypair", "encaps", "decaps"):
        summary = summarize(stats[op])
        if summary is None:
            print(f"  {op:7s} count=0")
            continue
        count, avg, min_v, max_v = summary
        print(
            f"  {op:7s} count={count:<4d} "
            f"avg={avg:10.2f} min={min_v:10d} max={max_v:10d}"
        )
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize cycle counts in Out/speed_*.txt files."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or glob patterns to summarize. Defaults to Out/speed_*.txt.",
    )
    return parser


def resolve_paths(patterns: list[str]) -> list[Path]:
    if not patterns:
        return sorted(Path(".").glob("Out/speed_*.txt"))

    resolved: list[Path] = []
    for pattern in patterns:
        matches = sorted(Path(".").glob(pattern))
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
