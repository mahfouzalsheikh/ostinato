from __future__ import annotations

import json
import subprocess
import unittest
from collections.abc import Sequence

from ostinato.diagnostics import Status, collect_report


class FakeRunner:
    def __init__(
        self,
        results: dict[tuple[str, ...], subprocess.CompletedProcess[str]],
    ) -> None:
        self.results = results
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        key = tuple(command)
        self.calls.append(key)
        return self.results[key]


def completed(
    command: tuple[str, ...],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


class DoctorTests(unittest.TestCase):
    def test_missing_commands_are_reported_without_running_them(self) -> None:
        runner = FakeRunner({})

        report = collect_report(which=lambda _name: None, runner=runner)

        command_checks = [
            check
            for check in report.checks
            if check.category in {"tool", "midi", "audio"}
        ]
        self.assertTrue(command_checks)
        self.assertTrue(all(check.status is Status.MISSING for check in command_checks))
        self.assertEqual(runner.calls, [])

    def test_connected_devices_are_available_and_empty_devices_untested(self) -> None:
        results = {
            ("aconnect", "--input"): completed(
                ("aconnect", "--input"), stdout="client 24: 'FR-4X'\n"
            ),
            ("amidi", "--list-devices"): completed(
                ("amidi", "--list-devices"), stdout="No hardware is attached.\n"
            ),
            ("aplay", "--list-devices"): completed(
                ("aplay", "--list-devices"), stdout="card 1: USB Audio\n"
            ),
            ("arecord", "--list-devices"): completed(
                ("arecord", "--list-devices"),
                returncode=1,
                stderr="device enumeration denied\n",
            ),
            ("pw-cli", "info", "0"): completed(
                ("pw-cli", "info", "0"), stdout="id: 0 type PipeWire:Interface:Core\n"
            ),
        }
        runner = FakeRunner(results)

        report = collect_report(which=lambda name: f"/usr/bin/{name}", runner=runner)
        by_name = {check.name: check for check in report.checks}

        self.assertEqual(by_name["ALSA sequencer ports"].status, Status.AVAILABLE)
        self.assertEqual(by_name["ALSA raw MIDI ports"].status, Status.UNTESTED)
        self.assertEqual(by_name["ALSA playback devices"].status, Status.AVAILABLE)
        self.assertEqual(by_name["ALSA capture devices"].status, Status.UNTESTED)
        self.assertEqual(by_name["PipeWire core"].status, Status.AVAILABLE)

    def test_json_output_has_stable_status_strings(self) -> None:
        report = collect_report(which=lambda _name: None, runner=FakeRunner({}))

        payload = json.loads(report.to_json())

        self.assertIsInstance(payload["checks"], list)
        statuses = {item["status"] for item in payload["checks"]}
        self.assertLessEqual(statuses, {"AVAILABLE", "MISSING", "UNTESTED"})

    def test_text_output_includes_columns(self) -> None:
        report = collect_report(which=lambda _name: None, runner=FakeRunner({}))

        output = report.to_text()

        self.assertIn("CATEGORY", output)
        self.assertIn("STATUS", output)
        self.assertIn("MISSING", output)


if __name__ == "__main__":
    unittest.main()
