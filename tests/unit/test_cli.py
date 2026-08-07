from __future__ import annotations

import contextlib
import io
import unittest
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
        run.assert_called_once_with(keys="zaq", json_output=True)


if __name__ == "__main__":
    unittest.main()
