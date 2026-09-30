from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import benchmark_to_latex as benchmark


def completed_log(*lines: str) -> str:
    return "\n".join(("==========================", *lines, "#", ""))


class BenchmarkToLatexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.input_dir = Path(self.temporary_directory.name) / "Out"
        self.input_dir.mkdir()

    def write(self, relative_path: str, content: str) -> Path:
        path = self.input_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def render(self) -> tuple[str, list[benchmark.SkippedFile]]:
        runs, skipped = benchmark.load_runs(self.input_dir)
        return benchmark.render_latex(benchmark.aggregate_runs(runs)), skipped

    def test_averages_multiple_runs_and_rounds_half_up(self) -> None:
        self.write(
            "benchmark_raw/crypto_kem_Example_128_m4_speed.run1.txt",
            completed_log("keypair cycles:", "1", "encaps cycles:", "10", "+"),
        )
        self.write(
            "benchmark_raw/crypto_kem_Example_128_m4_speed.run2.txt",
            completed_log("keypair cycles:", "2", "encaps cycles:", "11", "+"),
        )

        latex, skipped = self.render()

        self.assertEqual(skipped, [])
        self.assertIn(
            r"\newcommand{\ngccExampleOneTwoEightMFourSpeedKeypairCycles}{2}",
            latex,
        )
        self.assertIn(
            r"\newcommand{\ngccExampleOneTwoEightMFourSpeedEncapsCycles}{11}",
            latex,
        )
        self.assertIn("Sources:", latex)
        self.assertIn("total samples: 2", latex)

    def test_top_level_polynomial_log_is_averaged(self) -> None:
        self.write(
            "polyrq_speed_crypto_kem_DAWN_Prime_128_m4.txt",
            completed_log(
                "poly_ntt cycles:",
                "9033",
                "+",
                "poly_ntt cycles:",
                "9034",
                "+",
            ),
        )

        latex, skipped = self.render()

        self.assertEqual(skipped, [])
        self.assertIn(
            r"\newcommand{\ngccDawnPrimeOneTwoEightMFourPolyrqPolyNttCycles}{9034}",
            latex,
        )

    def test_single_stack_sample_is_emitted_unchanged(self) -> None:
        self.write(
            "benchmark_raw/crypto_kem_DAWN_Prime_128_m4_stack.run1.txt",
            completed_log("keypair stack usage:", "8760"),
        )

        latex, skipped = self.render()

        self.assertEqual(skipped, [])
        self.assertIn(
            r"\newcommand{\ngccDawnPrimeOneTwoEightMFourStackKeypairBytes}{8760}",
            latex,
        )
        self.assertNotIn("% Tables: complete schemes", latex)

    def test_rq_r2_and_scheme_tables_have_requested_layout(self) -> None:
        for implementation, offset in (("m4", 0), ("ref", 10)):
            speed_offset = 0 if implementation == "m4" else 1000
            self.write(
                f"benchmark_raw/crypto_kem_Example_128_{implementation}_speed.run1.txt",
                completed_log(
                    "keypair cycles:",
                    str(1001 + speed_offset),
                    "encaps cycles:",
                    str(2001 + speed_offset),
                    "decaps cycles:",
                    str(3001 + speed_offset),
                ),
            )
            self.write(
                f"benchmark_raw/crypto_kem_Example_128_{implementation}_stack.run1.txt",
                completed_log(
                    "keypair stack usage:",
                    str(4 + offset),
                    "encaps stack usage:",
                    str(5 + offset),
                    "decaps stack usage:",
                    str(6 + offset),
                ),
            )
            self.write(
                f"polyrq_speed_crypto_kem_Example_128_{implementation}.txt",
                completed_log("poly_ntt cycles:", str(7 + offset)),
            )
            r2_prefix = "r2_radix16_mul " if implementation == "m4" else "mul_in_R2_"
            self.write(
                f"polyr2_speed_crypto_kem_Example_128_{implementation}.txt",
                completed_log(
                    f"{r2_prefix}64 cycles:",
                    str(8 + offset),
                    f"{r2_prefix}128 cycles:",
                    str(9 + offset),
                    f"{r2_prefix}256 cycles:",
                    str(10 + offset),
                    *(
                        (
                            "r2_radix16_mul 256x128 cycles:",
                            str(11 + offset),
                        )
                        if implementation == "m4"
                        else ()
                    ),
                    "FastInversion cycles:",
                    str(12 + offset),
                ),
            )

        latex, skipped = self.render()

        self.assertEqual(skipped, [])
        rq_position = latex.index("% Tables: Rq polynomial operations")
        r2_position = latex.index("% Tables: R2 polynomial operations")
        scheme_position = latex.index("% Tables: complete schemes")
        self.assertLess(rq_position, r2_position)
        self.assertLess(r2_position, scheme_position)
        self.assertEqual(latex.count(r"\begin{table*}[htbp]"), 3)
        self.assertIn(
            (
                r"Schemes & NTT & INTT & Basemul & Baseinv & "
                r"$\mathrm{Sample}_f$ & $\mathrm{Sample}_g$"
            ),
            latex,
        )
        self.assertIn(
            (
                r"Example\_128 (M4) & "
                r"\ngccExampleOneTwoEightMFourPolyrqPolyNttCycles & -- & -- & -- & -- & --"
            ),
            latex,
        )
        self.assertIn(
            (
                r"Example\_128 (M4) & "
                r"\ngccExampleOneTwoEightMFourPolyrTwoRTwoRadixOneSixMulSixFourCycles & "
                r"\ngccExampleOneTwoEightMFourPolyrTwoRTwoRadixOneSixMulOneTwoEightCycles & "
                r"\ngccExampleOneTwoEightMFourPolyrTwoRTwoRadixOneSixMulTwoFiveSixCycles & "
                r"\ngccExampleOneTwoEightMFourPolyrTwoRTwoRadixOneSixMulTwoFiveSixXOneTwoEightCycles & "
                r"\ngccExampleOneTwoEightMFourPolyrTwoFastInversionCycles"
            ),
            latex,
        )
        m4_row = (
            r"\textbf{Example\_128 (M4)} & "
            r"\textbf{1k} & \textbf{2k} & \textbf{3k}"
        )
        ref_row = (
            r"Example\_128 (ref) & 2k & 3k & 4k"
        )
        self.assertIn(m4_row, latex)
        self.assertIn(ref_row, latex)
        self.assertLess(latex.index(m4_row), latex.index(ref_row))
        scheme_table = latex[scheme_position:]
        self.assertNotIn(r"\shortstack", scheme_table)
        self.assertNotIn("Stack", scheme_table)

    def test_tables_mark_unavailable_implementation_measurements(self) -> None:
        self.write(
            "polyrq_speed_crypto_kem_Example_128_m4.txt",
            completed_log("poly_ntt cycles:", "9"),
        )

        latex, skipped = self.render()

        self.assertEqual(skipped, [])
        self.assertIn(
            r"Example\_128 (ref) & -- & -- & -- & -- & -- & --",
            latex,
        )

    def test_malformed_metric_value_pair_is_rejected(self) -> None:
        path = self.write(
            "polyrq_speed_crypto_kem_Broken_128_m4.txt",
            completed_log("poly_ntt cycles:", "not-a-number"),
        )

        runs, skipped = benchmark.load_runs(self.input_dir)

        self.assertEqual(runs, [])
        self.assertEqual(skipped[0].source, path.name)
        self.assertIn("malformed value", skipped[0].reason)

    def test_malformed_metric_label_is_rejected(self) -> None:
        text = completed_log("poly_ntt! cycles:", "10")

        with self.assertRaisesRegex(benchmark.BenchmarkParseError, "metric label"):
            benchmark.parse_completed_log(text, "cycles")

    def test_inconsistent_operation_counts_are_rejected(self) -> None:
        self.write(
            "benchmark_raw/crypto_kem_Broken_128_m4_speed.run1.txt",
            completed_log(
                "keypair cycles:",
                "1",
                "encaps cycles:",
                "2",
                "+",
                "keypair cycles:",
                "3",
                "+",
            ),
        )

        runs, skipped = benchmark.load_runs(self.input_dir)

        self.assertEqual(runs, [])
        self.assertEqual(len(skipped), 1)
        self.assertIn("inconsistent operation sample counts", skipped[0].reason)

    def test_empty_and_incomplete_files_are_skipped_and_reported(self) -> None:
        self.write("polyr2_speed_crypto_kem_Empty_128_m4.txt", "")
        self.write(
            "polyrq_speed_crypto_kem_Interrupted_128_m4.txt",
            "poly_ntt cycles:\n10\n",
        )

        runs, skipped = benchmark.load_runs(self.input_dir)

        self.assertEqual(runs, [])
        self.assertEqual(len(skipped), 2)
        reasons = {item.source: item.reason for item in skipped}
        self.assertEqual(reasons["polyr2_speed_crypto_kem_Empty_128_m4.txt"], "empty file")
        self.assertIn("incomplete file", reasons["polyrq_speed_crypto_kem_Interrupted_128_m4.txt"])

    def test_top_level_experiments_and_named_variants_are_excluded(self) -> None:
        log = completed_log("keypair cycles:", "1")
        self.write("speed_crypto_kem_ZEN-128_m4.txt", log)
        self.write("speed_crypto_kem_ZEN-512_m4_direct_baseinv.txt", log)
        self.write("zenspeed_crypto_kem_ZEN-512_ref_origin.txt", log)

        specs, skipped = benchmark.discover_logs(self.input_dir)

        self.assertEqual(specs, [])
        reasons = {item.source: item.reason for item in skipped}
        self.assertIn("top-level speed experiment", reasons["speed_crypto_kem_ZEN-128_m4.txt"])
        self.assertIn("direct_baseinv", reasons["speed_crypto_kem_ZEN-512_m4_direct_baseinv.txt"])
        self.assertIn("ref_origin", reasons["zenspeed_crypto_kem_ZEN-512_ref_origin.txt"])

    def test_macro_name_collision_is_rejected(self) -> None:
        log = completed_log("poly_ntt cycles:", "1")
        self.write("polyrq_speed_crypto_kem_A-B_m4.txt", log)
        self.write("polyrq_speed_crypto_kem_A_B_m4.txt", log)
        runs, skipped = benchmark.load_runs(self.input_dir)

        self.assertEqual(skipped, [])
        with self.assertRaisesRegex(benchmark.MacroCollisionError, "collision"):
            benchmark.render_latex(benchmark.aggregate_runs(runs))


if __name__ == "__main__":
    unittest.main()
