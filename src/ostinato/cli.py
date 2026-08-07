"""Project Ostinato command-line interface."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from ostinato import __version__
from ostinato.diagnostics import collect_report
from ostinato.keyboard_input import run_keyboard


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""

    parser = argparse.ArgumentParser(
        prog="ostinato",
        description="FR-4X live arranger proof-of-concept tools",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser(
        "doctor",
        help="report host MIDI/audio readiness without changing the machine",
    )
    doctor.add_argument(
        "--json",
        action="store_true",
        help="write the diagnostic report as JSON",
    )

    keyboard = commands.add_parser(
        "keyboard",
        help="simulate normalized chord input with the computer keyboard",
    )
    keyboard.add_argument(
        "--keys",
        help="process this key sequence instead of reading an interactive terminal",
    )
    keyboard.add_argument(
        "--json",
        action="store_true",
        help="write one JSON object per input event",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""

    arguments = build_parser().parse_args(argv)
    if arguments.command == "doctor":
        report = collect_report()
        print(report.to_json() if arguments.json else report.to_text())
        return 0
    if arguments.command == "keyboard":
        return run_keyboard(keys=arguments.keys, json_output=arguments.json)
    return 2
