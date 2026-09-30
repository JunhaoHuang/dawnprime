#!/usr/bin/env python3
"""Convert completed canonical benchmark logs to LaTeX commands and tables."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


DONE_MARKER = "#"
DEFAULT_INPUT_DIR = Path("Out")
DEFAULT_OUTPUT = Path("Out/benchmark_results.tex")

TOP_LEVEL_RE = re.compile(
    r"^(?P<category>polyrq|polyr2)_speed_crypto_kem_"
    r"(?P<scheme>.+)_(?P<implementation>[^_]+)\.txt$"
)
RAW_RE = re.compile(
    r"^crypto_kem_(?P<scheme>.+)_(?P<implementation>[^_]+)_"
    r"(?P<category>speed|stack)\.run(?P<run>[0-9]+)\.txt$"
)
METRIC_RE = {
    "cycles": re.compile(r"^(?P<operation>[A-Za-z0-9][A-Za-z0-9 _-]*) cycles:$"),
    "bytes": re.compile(r"^(?P<operation>[A-Za-z0-9][A-Za-z0-9 _-]*) stack usage:$"),
}
METRIC_SUFFIXES = (" cycles:", " stack usage:")
DIGIT_WORDS = {
    "0": "Zero",
    "1": "One",
    "2": "Two",
    "3": "Three",
    "4": "Four",
    "5": "Five",
    "6": "Six",
    "7": "Seven",
    "8": "Eight",
    "9": "Nine",
}
CATEGORY_ORDER = {"speed": 0, "stack": 1, "polyrq": 2, "polyr2": 3}
IMPLEMENTATION_ORDER = ("m4", "ref")
KEM_OPERATIONS = ("keypair", "encaps", "decaps")
KEM_OPERATION_LABELS = {
    "keypair": "Key generation",
    "encaps": "Encapsulation",
    "decaps": "Decapsulation",
}
RQ_TABLE_COLUMNS = (
    ("poly_ntt", "NTT"),
    ("poly_intt", "INTT"),
    ("poly_basemul_ntt", "Basemul"),
    ("poly_baseinv_ntt", "Baseinv"),
    ("poly_generate_f", r"$\mathrm{Sample}_f$"),
    ("poly_generate_g", r"$\mathrm{Sample}_g$"),
)


class BenchmarkError(ValueError):
    """Base class for benchmark conversion failures."""


class BenchmarkParseError(BenchmarkError):
    """Raised when a completed log contains malformed measurements."""


class MacroCollisionError(BenchmarkError):
    """Raised when distinct measurements map to one LaTeX command name."""


@dataclass(frozen=True)
class LogSpec:
    path: Path
    source: str
    category: str
    scheme: str
    implementation: str
    unit: str


@dataclass(frozen=True)
class ParsedRun:
    spec: LogSpec
    operations: tuple[tuple[str, tuple[int, ...]], ...]


@dataclass(frozen=True)
class SkippedFile:
    source: str
    reason: str


@dataclass(frozen=True)
class MeasurementKey:
    category: str
    scheme: str
    implementation: str
    operation: str
    unit: str


@dataclass(frozen=True)
class SourceSamples:
    source: str
    count: int


@dataclass(frozen=True)
class AggregatedMeasurement:
    key: MeasurementKey
    samples: tuple[int, ...]
    sources: tuple[SourceSamples, ...]
    operation_order: int

    @property
    def rounded_mean(self) -> int:
        return round_half_up(self.samples)


@dataclass
class _MeasurementBuilder:
    samples: list[int] = field(default_factory=list)
    sources: list[SourceSamples] = field(default_factory=list)
    operation_order: int = 0


def relative_source(path: Path, input_dir: Path) -> str:
    try:
        return path.relative_to(input_dir).as_posix()
    except ValueError:
        return path.as_posix()


def discover_logs(input_dir: Path) -> tuple[list[LogSpec], list[SkippedFile]]:
    """Find canonical inputs and classify benchmark-like files that are excluded."""
    specs: list[LogSpec] = []
    skipped: list[SkippedFile] = []

    for path in sorted(input_dir.glob("*speed*.txt")):
        source = relative_source(path, input_dir)
        if "direct_baseinv" in path.name:
            skipped.append(SkippedFile(source, "excluded direct_baseinv experiment"))
            continue
        if "ref_origin" in path.name:
            skipped.append(SkippedFile(source, "excluded ref_origin experiment"))
            continue

        match = TOP_LEVEL_RE.fullmatch(path.name)
        if match is None:
            skipped.append(SkippedFile(source, "excluded top-level speed experiment"))
            continue

        specs.append(
            LogSpec(
                path=path,
                source=source,
                category=match.group("category"),
                scheme=match.group("scheme"),
                implementation=match.group("implementation"),
                unit="cycles",
            )
        )

    raw_dir = input_dir / "benchmark_raw"
    for path in sorted(raw_dir.glob("*.run*.txt")):
        source = relative_source(path, input_dir)
        if "direct_baseinv" in path.name:
            skipped.append(SkippedFile(source, "excluded direct_baseinv experiment"))
            continue
        if "ref_origin" in path.name:
            skipped.append(SkippedFile(source, "excluded ref_origin experiment"))
            continue

        match = RAW_RE.fullmatch(path.name)
        if match is None:
            if "_hashing.run" in path.name:
                reason = "excluded unsupported hashing benchmark"
            else:
                reason = "unrecognized raw benchmark filename"
            skipped.append(SkippedFile(source, reason))
            continue

        category = match.group("category")
        specs.append(
            LogSpec(
                path=path,
                source=source,
                category=category,
                scheme=match.group("scheme"),
                implementation=match.group("implementation"),
                unit="bytes" if category == "stack" else "cycles",
            )
        )

    specs.sort(key=lambda spec: spec.source)
    skipped.sort(key=lambda item: item.source)
    return specs, skipped


def parse_completed_log(text: str, unit: str) -> tuple[tuple[str, tuple[int, ...]], ...]:
    """Parse one completed log, preserving its first-seen operation order."""
    lines = [line.strip() for line in text.splitlines()]
    nonempty_lines = [line for line in lines if line]
    if not nonempty_lines:
        raise BenchmarkParseError("empty file")
    if nonempty_lines[-1] != DONE_MARKER:
        raise BenchmarkParseError(f"incomplete file (missing terminal {DONE_MARKER!r})")

    try:
        metric_re = METRIC_RE[unit]
    except KeyError as exc:
        raise BenchmarkParseError(f"unsupported unit {unit!r}") from exc

    values_by_operation: dict[str, list[int]] = {}
    operation_order: list[str] = []

    for index, line in enumerate(lines):
        if not line.endswith(METRIC_SUFFIXES):
            continue

        match = metric_re.fullmatch(line)
        if match is None:
            raise BenchmarkParseError(f"line {index + 1}: malformed or unexpected metric label {line!r}")
        if index + 1 >= len(lines) or re.fullmatch(r"[0-9]+", lines[index + 1]) is None:
            value = lines[index + 1] if index + 1 < len(lines) else "<end of file>"
            raise BenchmarkParseError(
                f"line {index + 1}: metric {line!r} has malformed value {value!r}"
            )

        operation = match.group("operation")
        if operation not in values_by_operation:
            values_by_operation[operation] = []
            operation_order.append(operation)
        values_by_operation[operation].append(int(lines[index + 1]))

    if not values_by_operation:
        raise BenchmarkParseError("completed file contains no measurements")

    counts = {operation: len(values) for operation, values in values_by_operation.items()}
    if len(set(counts.values())) != 1:
        detail = ", ".join(f"{operation}={count}" for operation, count in counts.items())
        raise BenchmarkParseError(f"inconsistent operation sample counts ({detail})")

    return tuple((operation, tuple(values_by_operation[operation])) for operation in operation_order)


def load_runs(input_dir: Path) -> tuple[list[ParsedRun], list[SkippedFile]]:
    if not input_dir.is_dir():
        raise BenchmarkError(f"input directory does not exist: {input_dir}")

    specs, skipped = discover_logs(input_dir)
    runs: list[ParsedRun] = []
    for spec in specs:
        try:
            text = spec.path.read_text(encoding="utf-8", errors="replace")
            operations = parse_completed_log(text, spec.unit)
        except (OSError, BenchmarkParseError) as exc:
            skipped.append(SkippedFile(spec.source, str(exc)))
            continue
        runs.append(ParsedRun(spec, operations))

    skipped.sort(key=lambda item: item.source)
    return runs, skipped


def aggregate_runs(runs: Iterable[ParsedRun]) -> list[AggregatedMeasurement]:
    builders: dict[MeasurementKey, _MeasurementBuilder] = {}
    next_operation_order: dict[tuple[str, str, str], int] = {}

    for run in sorted(runs, key=lambda item: item.spec.source):
        group_key = (run.spec.category, run.spec.scheme, run.spec.implementation)
        for operation, samples in run.operations:
            key = MeasurementKey(
                category=run.spec.category,
                scheme=run.spec.scheme,
                implementation=run.spec.implementation,
                operation=operation,
                unit=run.spec.unit,
            )
            if key not in builders:
                order = next_operation_order.get(group_key, 0)
                builders[key] = _MeasurementBuilder(operation_order=order)
                next_operation_order[group_key] = order + 1
            builder = builders[key]
            builder.samples.extend(samples)
            builder.sources.append(SourceSamples(run.spec.source, len(samples)))

    measurements = [
        AggregatedMeasurement(
            key=key,
            samples=tuple(builder.samples),
            sources=tuple(builder.sources),
            operation_order=builder.operation_order,
        )
        for key, builder in builders.items()
    ]
    measurements.sort(key=measurement_sort_key)
    return measurements


def measurement_sort_key(measurement: AggregatedMeasurement) -> tuple[object, ...]:
    key = measurement.key
    return (
        CATEGORY_ORDER.get(key.category, len(CATEGORY_ORDER)),
        key.category,
        key.scheme,
        key.implementation,
        measurement.operation_order,
        key.operation,
    )


def round_half_up(samples: Sequence[int]) -> int:
    """Return the integer arithmetic mean, rounding exact halves upward."""
    if not samples:
        raise BenchmarkError("cannot average zero samples")
    if any(value < 0 for value in samples):
        raise BenchmarkError("benchmark samples must be non-negative")
    total = sum(samples)
    count = len(samples)
    return (2 * total + count) // (2 * count)


def macro_component(value: str) -> str:
    pieces: list[str] = []
    for token in re.findall(r"[A-Za-z]+|[0-9]", value):
        if token.isdigit():
            pieces.append(DIGIT_WORDS[token])
        elif token.isupper() or token.islower():
            pieces.append(token.lower().capitalize())
        else:
            pieces.append(token[0].upper() + token[1:])
    if not pieces:
        raise BenchmarkError(f"cannot form a LaTeX command component from {value!r}")
    return "".join(pieces)


def macro_name(key: MeasurementKey) -> str:
    name = "ngcc" + "".join(
        macro_component(component)
        for component in (
            key.scheme,
            key.implementation,
            key.category,
            key.operation,
            key.unit,
        )
    )
    if re.fullmatch(r"[A-Za-z]+", name) is None:
        raise BenchmarkError(f"generated invalid LaTeX command name {name!r}")
    return name


def latex_escape(value: str) -> str:
    """Escape characters that can occur in benchmark labels."""
    return re.sub(r"([#$%&_{}])", lambda match: "\\" + match.group(1), value)


def table_value(measurement: AggregatedMeasurement | None) -> str:
    """Render a measurement as its generated command, or an explicit gap."""
    if measurement is None:
        return "--"
    return rf"\{macro_name(measurement.key)}"


def kilocycle_value(measurement: AggregatedMeasurement | None) -> str:
    """Render whole kilo-cycles, truncating cycles below the next thousand."""
    if measurement is None:
        return "--"
    return f"{measurement.rounded_mean // 1000}k"


def scheme_display_name(scheme: str) -> str:
    """Format internal scheme identifiers for paper tables."""
    dawn_match = re.fullmatch(r"DAWN_Prime_([0-9]+)", scheme)
    if dawn_match is not None:
        return rf"DAWN$^\prime$-{dawn_match.group(1)}"
    return latex_escape(scheme)


def scheme_row_label(scheme: str, implementation: str) -> str:
    implementation_label = "M4" if implementation == "m4" else "ref"
    return f"{scheme_display_name(scheme)} ({implementation_label})"


def scheme_parameter(scheme: str) -> int | None:
    """Return n/4, encoded by the trailing scheme security parameter."""
    match = re.search(r"([0-9]+)$", scheme)
    return int(match.group(1)) if match is not None else None


def category_lookup(
    measurements: Sequence[AggregatedMeasurement], category: str
) -> tuple[
    list[str],
    dict[tuple[str, str, str], AggregatedMeasurement],
]:
    selected = [
        measurement
        for measurement in measurements
        if measurement.key.category == category
        and measurement.key.implementation in IMPLEMENTATION_ORDER
    ]
    lookup = {
        (measurement.key.scheme, measurement.key.implementation, measurement.key.operation): measurement
        for measurement in selected
    }
    schemes = sorted({measurement.key.scheme for measurement in selected})
    return schemes, lookup


def render_rq_table(measurements: Sequence[AggregatedMeasurement]) -> list[str]:
    """Render Rq operations as columns and scheme implementations as rows."""
    schemes, lookup = category_lookup(measurements, "polyrq")
    if not schemes:
        return []

    lines = [
        "",
        "% Tables: Rq polynomial operations",
        "",
        r"\begin{table*}[htbp]",
        r"\centering",
        r"\small",
        (
            r"\caption{Performance of core operations over $R_q$ on ARM Cortex-M4 "
            r"(cycles).}"
        ),
        r"\label{tab:polyrq}",
        r"\begin{tabular}{l|r|r|r|r|r|r}",
        r"\hline",
        "Schemes & " + " & ".join(label for _, label in RQ_TABLE_COLUMNS) + r" \\",
        r"\hline",
    ]
    for scheme_index, scheme in enumerate(schemes):
        for implementation in IMPLEMENTATION_ORDER:
            values = [
                table_value(lookup.get((scheme, implementation, operation)))
                for operation, _ in RQ_TABLE_COLUMNS
            ]
            lines.append(
                scheme_row_label(scheme, implementation)
                + " & "
                + " & ".join(values)
                + r" \\"
            )
        lines.append(r"\hline\hline" if scheme_index + 1 < len(schemes) else r"\hline")

    lines.extend([r"\end{tabular}", r"\end{table*}"])
    return lines


def r2_table_measurement(
    lookup: dict[tuple[str, str, str], AggregatedMeasurement],
    scheme: str,
    implementation: str,
    size: str,
) -> AggregatedMeasurement | None:
    """Select the optimized M4 or conventional reference R2 multiplier."""
    if implementation == "m4":
        operations = (f"r2_radix16_mul {size}", f"mul_in_R2_{size}")
    else:
        operations = (f"mul_in_R2_{size}", f"r2_radix16_mul {size}")
    for operation in operations:
        measurement = lookup.get((scheme, implementation, operation))
        if measurement is not None:
            return measurement
    return None


def render_r2_table(measurements: Sequence[AggregatedMeasurement]) -> list[str]:
    """Render the core R2 multiplications in the same layout as the paper table."""
    schemes, lookup = category_lookup(measurements, "polyr2")
    if not schemes:
        return []

    lines = [
        "",
        "% Tables: R2 polynomial operations",
        "",
        r"\begin{table*}[htbp]",
        r"\centering",
        r"\small",
        (
            r"\caption{Performance of polynomial multiplication over $R_2$ on ARM "
            r"Cortex-M4 (cycles).}"
        ),
        r"\label{tab:polyr2}",
        r"\begin{tabular}{l|r|r|r|r|r}",
        r"\hline",
        (
            r"Schemes & $\mathrm{polymul}_{64}$ & $\mathrm{polymul}_{n/4}$ & "
            r"$\mathrm{polymul}_{n/2}$ & $\mathrm{polymul}_{n/2\times n/4}$ & "
            r"FastInversion \\"
        ),
        r"\hline",
    ]
    for scheme_index, scheme in enumerate(schemes):
        parameter = scheme_parameter(scheme)
        for implementation in IMPLEMENTATION_ORDER:
            if parameter is None:
                multiplication_values = ["--"] * 4
            else:
                n4 = parameter
                n2 = 2 * parameter
                sizes = ("64", str(n4), str(n2), f"{n2}x{n4}")
                multiplication_values = [
                    table_value(
                        r2_table_measurement(
                            lookup, scheme, implementation, size
                        )
                    )
                    for size in sizes
                ]
            inversion = table_value(
                lookup.get((scheme, implementation, "FastInversion"))
            )
            lines.append(
                scheme_row_label(scheme, implementation)
                + " & "
                + " & ".join((*multiplication_values, inversion))
                + r" \\"
            )
        lines.append(r"\hline\hline" if scheme_index + 1 < len(schemes) else r"\hline")

    lines.extend([r"\end{tabular}", r"\end{table*}"])
    return lines


def render_scheme_table(
    measurements: Sequence[AggregatedMeasurement],
) -> list[str]:
    """Render KEM speed measurements in whole kilo-cycles."""
    selected = [
        measurement
        for measurement in measurements
        if measurement.key.category == "speed"
        and measurement.key.implementation in IMPLEMENTATION_ORDER
        and measurement.key.operation in KEM_OPERATIONS
    ]
    if not selected:
        return []

    lookup = {
        (
            measurement.key.scheme,
            measurement.key.implementation,
            measurement.key.operation,
        ): measurement
        for measurement in selected
    }
    schemes = sorted({measurement.key.scheme for measurement in selected})
    lines = [
        "",
        "% Tables: complete schemes",
        "",
        r"\begin{table*}[htbp]",
        r"\centering",
        r"\small",
        r"\caption{Performance of KEM schemes on ARM Cortex-M4 (in kilo-cycles).}",
        r"\label{tab:scheme-speed}",
        r"\begin{tabular}{l|r|r|r}",
        r"\hline",
        (
            "Scheme & "
            + " & ".join(KEM_OPERATION_LABELS[operation] for operation in KEM_OPERATIONS)
            + r" \\"
        ),
        r"\hline",
    ]

    for scheme_index, scheme in enumerate(schemes):
        for implementation in IMPLEMENTATION_ORDER:
            if not any(
                (scheme, implementation, operation) in lookup
                for operation in KEM_OPERATIONS
            ):
                continue

            cells = [
                kilocycle_value(lookup.get((scheme, implementation, operation)))
                for operation in KEM_OPERATIONS
            ]
            if implementation == "m4":
                row_label = rf"\textbf{{{scheme_row_label(scheme, implementation)}}}"
                cells = [rf"\textbf{{{value}}}" for value in cells]
            else:
                row_label = scheme_row_label(scheme, implementation)
            row = row_label + " & " + " & ".join(cells)
            lines.append(row + r" \\")
        lines.append(r"\hline\hline" if scheme_index + 1 < len(schemes) else r"\hline")

    lines.extend(
        [
            r"\end{tabular}",
            r"\end{table*}",
        ]
    )
    return lines


def render_latex(measurements: Sequence[AggregatedMeasurement]) -> str:
    names: dict[str, MeasurementKey] = {}
    for measurement in measurements:
        name = macro_name(measurement.key)
        previous = names.get(name)
        if previous is not None and previous != measurement.key:
            raise MacroCollisionError(
                f"LaTeX command collision for {name!r}: {previous!r} and {measurement.key!r}"
            )
        names[name] = measurement.key

    lines = [
        "% Generated by benchmark_to_latex.py. Do not edit.",
        "% Values are arithmetic means rounded half-up to whole cycles or bytes.",
    ]
    previous_category: str | None = None
    previous_scheme: str | None = None
    previous_implementation: str | None = None

    for measurement in measurements:
        key = measurement.key
        if key.category != previous_category:
            lines.extend(["", f"% Category: {key.category}"])
            previous_category = key.category
            previous_scheme = None
            previous_implementation = None
        if key.scheme != previous_scheme:
            lines.extend(["", f"% Scheme: {key.scheme}"])
            previous_scheme = key.scheme
            previous_implementation = None
        if key.implementation != previous_implementation:
            lines.append(f"% Implementation: {key.implementation}")
            previous_implementation = key.implementation

        source_label = "Source" if len(measurement.sources) == 1 else "Sources"
        source_text = ", ".join(
            f"{source.source} ({source.count} samples)" for source in measurement.sources
        )
        lines.append(
            f"% {source_label}: {source_text}; total samples: {len(measurement.samples)}"
        )
        lines.append(
            rf"\newcommand{{\{macro_name(key)}}}{{{measurement.rounded_mean}}}"
        )

    lines.extend(render_rq_table(measurements))
    lines.extend(render_r2_table(measurements))
    lines.extend(render_scheme_table(measurements))

    return "\n".join(lines) + "\n"


def write_latex(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Average canonical benchmark logs and emit LaTeX commands and tables.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        runs, skipped = load_runs(args.input_dir)
        measurements = aggregate_runs(runs)
        if not measurements:
            raise BenchmarkError("no complete canonical benchmark measurements found")
        content = render_latex(measurements)
        write_latex(args.output, content)
    except (BenchmarkError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for item in skipped:
        print(f"skipped {item.source}: {item.reason}", file=sys.stderr)
    print(
        f"wrote {len(measurements)} measurements and their tables to {args.output} "
        f"from {len(runs)} completed files; skipped {len(skipped)} files"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
