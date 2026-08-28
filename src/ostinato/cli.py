"""Project Ostinato command-line interface."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from ostinato import __version__
from ostinato.computer_audio import run_audible_keyboard
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
    keyboard.add_argument(
        "--play",
        action="store_true",
        help="play the built-in modern tango through the computer audio output",
    )
    keyboard.add_argument(
        "--tempo",
        type=int,
        default=120,
        metavar="BPM",
        help="audible demo tempo from 40 to 240 BPM (default: 120)",
    )

    web = commands.add_parser(
        "web",
        help="serve the real-time MIDI monitor and accordion surface",
    )
    web.add_argument(
        "--host",
        default="127.0.0.1",
        help="listen address (default: 127.0.0.1)",
    )
    web.add_argument(
        "--port",
        type=int,
        default=8765,
        help="listen port from 1 to 65535 (default: 8765)",
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
        if arguments.play:
            return run_audible_keyboard(
                keys=arguments.keys,
                json_output=arguments.json,
                tempo_bpm=arguments.tempo,
            )
        return run_keyboard(
            keys=arguments.keys,
            json_output=arguments.json,
            tempo_bpm=arguments.tempo,
        )
    if arguments.command == "web":
        if not 1 <= arguments.port <= 65535:
            build_parser().error("web --port must be from 1 to 65535")
        from ostinato.web_server import run_web

        return run_web(host=arguments.host, port=arguments.port)
    return 2
