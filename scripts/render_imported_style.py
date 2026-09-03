#!/usr/bin/env python3
"""Render one imported KORG Chord Variation to an offline WAV reference."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from ostinato.styles.importers.korg.midi_style_importer import (
    UnsupportedKorgStyleFormat,
)
from ostinato.styles.importers.korg.pa80_smf import inspect_pa80_smf_directory
from ostinato.styles.models import StyleElementType
from ostinato.styles.offline_audio import render_style_variation_to_wav


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Pa80 Chord Variation directory")
    parser.add_argument("--name", required=True, help="style name")
    parser.add_argument(
        "--element",
        choices=[value.value for value in StyleElementType],
        default=StyleElementType.VARIATION_1.value,
    )
    parser.add_argument("--cv", type=int, default=1, help="Chord Variation number")
    parser.add_argument("--tempo", type=int, help="explicit listening tempo in BPM")
    parser.add_argument(
        "--soundfont",
        type=Path,
        help="GM SoundFont (default: exact OSTINATO_SOUNDFONT value)",
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    soundfont = arguments.soundfont
    if soundfont is None:
        configured = os.environ.get("OSTINATO_SOUNDFONT")
        if configured:
            soundfont = Path(configured)
    if soundfont is None:
        build_parser().error(
            "pass --soundfont or set OSTINATO_SOUNDFONT; no file is guessed"
        )
    try:
        result = inspect_pa80_smf_directory(arguments.input, style_name=arguments.name)
        report = render_style_variation_to_wav(
            result.style,
            arguments.output,
            soundfont,
            element_type=StyleElementType(arguments.element),
            chord_variation=arguments.cv,
            tempo_bpm=arguments.tempo,
        )
    except (OSError, UnsupportedKorgStyleFormat, ValueError) as error:
        build_parser().error(str(error))
    print(f"Rendered: {report.output_path}")
    print(
        f"  {report.element_type.value} CV{report.chord_variation}: "
        f"{report.note_count} notes, {report.duration_seconds:.2f} seconds"
    )
    print("  Programs: General MIDI approximation; source KORG banks preserved in JSON")
    print("  Pitch transform: none (fixed-source listening reference)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
