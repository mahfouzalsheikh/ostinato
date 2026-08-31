from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ostinato.cli import build_parser, main
from ostinato.diagnostics import Check, DoctorReport, Status


class CliTests(unittest.TestCase):
    def test_doctor_subcommand_is_required(self) -> None:
        parser = build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args([])

    def test_doctor_prints_report_and_succeeds(self) -> None:
        report = DoctorReport(
            (Check("runtime", "python", Status.AVAILABLE, "test runtime"),)
        )
        output = io.StringIO()

        with (
            patch("ostinato.cli.collect_report", return_value=report),
            contextlib.redirect_stdout(output),
        ):
            exit_code = main(["doctor"])

        self.assertEqual(exit_code, 0)
        self.assertIn("AVAILABLE", output.getvalue())

    def test_doctor_json_is_machine_readable(self) -> None:
        report = DoctorReport(
            (Check("runtime", "python", Status.AVAILABLE, "test runtime"),)
        )
        output = io.StringIO()

        with (
            patch("ostinato.cli.collect_report", return_value=report),
            contextlib.redirect_stdout(output),
        ):
            exit_code = main(["doctor", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertIn('"status": "AVAILABLE"', output.getvalue())

    def test_keyboard_command_delegates_to_simulator(self) -> None:
        with patch("ostinato.cli.run_keyboard", return_value=0) as run:
            exit_code = main(["keyboard", "--keys", "zaq", "--json"])

        self.assertEqual(exit_code, 0)
        run.assert_called_once_with(keys="zaq", json_output=True, tempo_bpm=120)

    def test_keyboard_play_delegates_to_audible_demo(self) -> None:
        with patch("ostinato.cli.run_audible_keyboard", return_value=0) as run:
            exit_code = main(["keyboard", "--play", "--tempo", "96"])

        self.assertEqual(exit_code, 0)
        run.assert_called_once_with(keys=None, json_output=False, tempo_bpm=96)

    def test_web_command_delegates_to_server(self) -> None:
        with patch("ostinato.web_server.run_web", return_value=0) as run:
            exit_code = main(["web", "--host", "0.0.0.0", "--port", "8123"])

        self.assertEqual(exit_code, 0)
        run.assert_called_once_with(host="0.0.0.0", port=8123)

    def test_soundfont_comparison_delegates_with_explicit_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            output = Path(temporary_name) / "comparison"
            with patch(
                "ostinato.cli.render_soundfont_comparison", return_value=(object(),)
            ) as render:
                exit_code = main(
                    [
                        "soundfont-compare",
                        "--output",
                        str(output),
                        "--style",
                        "classic_waltz",
                        "--hq",
                        "/sounds/hq.sf3",
                        "--legacy",
                        "/sounds/legacy.sf2",
                    ]
                )

        self.assertEqual(exit_code, 0)
        output_path, styles, variants = render.call_args.args
        self.assertEqual(output_path, output)
        self.assertEqual(styles, ("classic_waltz",))
        self.assertEqual([variant.id for variant in variants], ["hq", "legacy"])

    def test_waltz_comparison_uses_configured_open_sample_rack(self) -> None:
        sfz_paths = object()
        with tempfile.TemporaryDirectory() as temporary_name:
            output = Path(temporary_name) / "comparison"
            with (
                patch.dict("os.environ", {"OSTINATO_SOUNDFONT": "/sounds/hq.sf3"}),
                patch(
                    "ostinato.cli.SfzWaltzPaths.from_environment",
                    return_value=sfz_paths,
                ),
                patch(
                    "ostinato.cli.render_waltz_realism_comparison",
                    return_value=(object(), object()),
                ) as render,
            ):
                exit_code = main(["waltz-compare", "--output", str(output)])

        self.assertEqual(exit_code, 0)
        render.assert_called_once_with(output, Path("/sounds/hq.sf3"), sfz_paths)

    def test_sfz_comparison_uses_all_builtins_by_default(self) -> None:
        sfz_paths = object()
        with tempfile.TemporaryDirectory() as temporary_name:
            output = Path(temporary_name) / "comparison"
            with (
                patch.dict("os.environ", {"OSTINATO_SOUNDFONT": "/sounds/hq.sf3"}),
                patch(
                    "ostinato.cli.SfzStylePaths.from_environment",
                    return_value=sfz_paths,
                ),
                patch(
                    "ostinato.cli.render_open_sample_comparison",
                    return_value=(object(), object()),
                ) as render,
            ):
                exit_code = main(["sfz-compare", "--output", str(output)])

        self.assertEqual(exit_code, 0)
        output_path, styles, soundfont, configured_paths = render.call_args.args
        self.assertEqual(output_path, output)
        self.assertEqual(len(styles), 14)
        self.assertEqual(soundfont, Path("/sounds/hq.sf3"))
        self.assertIs(configured_paths, sfz_paths)


if __name__ == "__main__":
    unittest.main()
