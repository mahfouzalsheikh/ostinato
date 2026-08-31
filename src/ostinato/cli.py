"""Project Ostinato command-line interface."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

from ostinato import __version__
from ostinato.computer_audio import DEMO_STYLES, run_audible_keyboard
from ostinato.diagnostics import collect_report
from ostinato.keyboard_input import run_keyboard
from ostinato.sfz_audio import SfzStylePaths, SfzWaltzPaths
from ostinato.soundfont_compare import (
    SoundFontVariant,
    render_open_sample_comparison,
    render_soundfont_comparison,
    render_waltz_realism_comparison,
)


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

    comparison = commands.add_parser(
        "soundfont-compare",
        help="render matched HQ and legacy SoundFont WAV files",
    )
    comparison.add_argument(
        "--output",
        required=True,
        type=Path,
        metavar="DIRECTORY",
        help="directory for WAV pairs and manifest.json",
    )
    comparison.add_argument(
        "--style",
        choices=("all", *DEMO_STYLES),
        default="all",
        help="style to render (default: all)",
    )
    comparison.add_argument(
        "--hq",
        type=Path,
        help="HQ SoundFont path (default: OSTINATO_SOUNDFONT)",
    )
    comparison.add_argument(
        "--legacy",
        type=Path,
        help="legacy SoundFont path (default: OSTINATO_LEGACY_SOUNDFONT)",
    )
    waltz_comparison = commands.add_parser(
        "waltz-compare",
        help="render GM and dedicated open-sample Classic Waltz WAV files",
    )
    waltz_comparison.add_argument(
        "--output",
        required=True,
        type=Path,
        metavar="DIRECTORY",
        help="directory for the WAV pair and manifest.json",
    )
    sfz_comparison = commands.add_parser(
        "sfz-compare",
        help="render GM and genre-profiled open-sample WAV files",
    )
    sfz_comparison.add_argument(
        "--output",
        required=True,
        type=Path,
        metavar="DIRECTORY",
        help="directory for WAV pairs and manifest.json",
    )
    sfz_comparison.add_argument(
        "--style",
        choices=("all", *DEMO_STYLES),
        default="all",
        help="style to render (default: all)",
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
    if arguments.command == "soundfont-compare":
        hq_path = arguments.hq or _environment_path("OSTINATO_SOUNDFONT")
        legacy_path = arguments.legacy or _environment_path("OSTINATO_LEGACY_SOUNDFONT")
        style_ids = (
            tuple(DEMO_STYLES) if arguments.style == "all" else (arguments.style,)
        )
        results = render_soundfont_comparison(
            arguments.output,
            style_ids,
            (
                SoundFontVariant("hq", "MuseScore General HQ", hq_path),
                SoundFontVariant("legacy", "TimGM6mb", legacy_path),
            ),
        )
        print(f"Rendered {len(results)} files and manifest.json in {arguments.output}")
        return 0
    if arguments.command == "waltz-compare":
        waltz_paths = SfzWaltzPaths.from_environment()
        if waltz_paths is None:
            build_parser().error("the Classic Waltz SFZ environment is required")
        results = render_waltz_realism_comparison(
            arguments.output,
            _environment_path("OSTINATO_SOUNDFONT"),
            waltz_paths,
        )
        print(f"Rendered {len(results)} files and manifest.json in {arguments.output}")
        return 0
    if arguments.command == "sfz-compare":
        style_paths = SfzStylePaths.from_environment()
        if style_paths is None:
            build_parser().error("the built-in style SFZ environment is required")
        style_ids = (
            tuple(DEMO_STYLES) if arguments.style == "all" else (arguments.style,)
        )
        results = render_open_sample_comparison(
            arguments.output,
            style_ids,
            _environment_path("OSTINATO_SOUNDFONT"),
            style_paths,
        )
        print(f"Rendered {len(results)} files and manifest.json in {arguments.output}")
        return 0
    return 2


def _environment_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        build_parser().error(f"{name} is required when no path option is supplied")
    return Path(value)
