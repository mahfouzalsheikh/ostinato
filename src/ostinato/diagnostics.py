"""Read-only diagnostics for the Ostinato host.

The probes in this module never open a MIDI port, start an audio stream, or
alter machine configuration. Command failures are data in the report rather
than fatal errors so the command is useful on an incompletely prepared host.
"""

from __future__ import annotations

import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Protocol


class Status(StrEnum):
    """Diagnostic result status."""

    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    UNTESTED = "UNTESTED"


@dataclass(frozen=True, slots=True)
class Check:
    """One host capability observation."""

    category: str
    name: str
    status: Status
    detail: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Complete diagnostic report."""

    checks: tuple[Check, ...]

    def to_json(self) -> str:
        """Serialize the report for tooling and evidence capture."""

        return json.dumps(
            {"checks": [asdict(check) for check in self.checks]},
            indent=2,
        )

    def to_text(self) -> str:
        """Render a concise terminal report."""

        widths = {
            "category": max(len("CATEGORY"), *(len(c.category) for c in self.checks)),
            "name": max(len("NAME"), *(len(c.name) for c in self.checks)),
            "status": max(len("STATUS"), *(len(c.status) for c in self.checks)),
        }
        header = (
            f"{'CATEGORY':<{widths['category']}}  "
            f"{'NAME':<{widths['name']}}  "
            f"{'STATUS':<{widths['status']}}  DETAIL"
        )
        separator = "-" * len(header)
        rows = [header, separator]
        rows.extend(
            f"{check.category:<{widths['category']}}  "
            f"{check.name:<{widths['name']}}  "
            f"{check.status:<{widths['status']}}  {check.detail}"
            for check in self.checks
        )
        return "\n".join(rows)


class CompletedCommand(Protocol):
    """The subprocess result fields used by diagnostics."""

    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[Sequence[str]], CompletedCommand]
Which = Callable[[str], str | None]


def _run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=3,
    )


def _first_line(value: str) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return lines[0] if lines else "no output"


def _tool_check(name: str, which: Which) -> Check:
    path = which(name)
    if path is None:
        return Check("tool", name, Status.MISSING, "executable not found on PATH")
    return Check("tool", name, Status.AVAILABLE, path)


def _device_check(
    *,
    category: str,
    name: str,
    command: Sequence[str],
    empty_markers: tuple[str, ...],
    which: Which,
    runner: Runner,
) -> Check:
    executable = command[0]
    if which(executable) is None:
        return Check(
            category,
            name,
            Status.MISSING,
            f"cannot probe because {executable!r} is not on PATH",
        )

    try:
        result = runner(command)
    except (OSError, subprocess.SubprocessError) as error:
        return Check(category, name, Status.UNTESTED, f"probe failed: {error}")

    combined = "\n".join((result.stdout, result.stderr)).strip()
    normalized = combined.casefold()
    if result.returncode != 0:
        return Check(
            category,
            name,
            Status.UNTESTED,
            f"probe exited {result.returncode}: {_first_line(combined)}",
        )
    if not combined or any(marker in normalized for marker in empty_markers):
        return Check(
            category,
            name,
            Status.UNTESTED,
            "probe succeeded but no connected device was reported",
        )
    return Check(category, name, Status.AVAILABLE, _first_line(combined))


def collect_report(
    *,
    which: Which = shutil.which,
    runner: Runner = _run_command,
) -> DoctorReport:
    """Collect non-mutating host diagnostics.

    ``which`` and ``runner`` are injectable to keep tests independent of host
    MIDI and audio hardware.
    """

    python_supported = sys.version_info >= (3, 12) and sys.version_info < (3, 14)
    checks: list[Check] = [
        Check(
            "runtime",
            "python",
            Status.AVAILABLE if python_supported else Status.MISSING,
            f"{platform.python_version()} at {sys.executable}",
        ),
        Check(
            "runtime",
            "platform",
            Status.AVAILABLE,
            platform.platform(),
        ),
    ]

    for module, distribution in (
        ("mido", "mido"),
        ("rtmidi", "python-rtmidi"),
        ("yaml", "PyYAML"),
    ):
        available = importlib.util.find_spec(module) is not None
        checks.append(
            Check(
                "python-package",
                distribution,
                Status.AVAILABLE if available else Status.MISSING,
                "importable" if available else "install the 'midi' optional extra",
            )
        )

    for tool in ("fluidsynth", "aconnect", "amidi", "aplay", "arecord", "pw-cli"):
        checks.append(_tool_check(tool, which))

    checks.extend(
        (
            _device_check(
                category="midi",
                name="ALSA sequencer ports",
                command=("aconnect", "--input"),
                empty_markers=("no clients", "no ports"),
                which=which,
                runner=runner,
            ),
            _device_check(
                category="midi",
                name="ALSA raw MIDI ports",
                command=("amidi", "--list-devices"),
                empty_markers=("no hardware", "no devices", "no sound card"),
                which=which,
                runner=runner,
            ),
            _device_check(
                category="audio",
                name="ALSA playback devices",
                command=("aplay", "--list-devices"),
                empty_markers=("no soundcards", "no devices"),
                which=which,
                runner=runner,
            ),
            _device_check(
                category="audio",
                name="ALSA capture devices",
                command=("arecord", "--list-devices"),
                empty_markers=("no soundcards", "no devices"),
                which=which,
                runner=runner,
            ),
            _device_check(
                category="audio",
                name="PipeWire core",
                command=("pw-cli", "info", "0"),
                empty_markers=("no objects",),
                which=which,
                runner=runner,
            ),
        )
    )
    return DoctorReport(tuple(checks))
