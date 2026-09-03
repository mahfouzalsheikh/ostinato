#!/usr/bin/env python3
"""Import KORG style MIDI exports into vendor-neutral JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ostinato.styles.importers.korg.midi_style_importer import (
    UnsupportedKorgStyleFormat,
    diagnostics_to_dict,
    inspect_korg_midi_style,
)
from ostinato.styles.importers.korg.pa80_smf import (
    inspect_pa80_smf_directory,
    pa80_diagnostics_to_dict,
)
from ostinato.styles.models import style_to_dict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        help="marker-based style MIDI file or Pa80 per-Chord-Variation directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="converted style directory (default: ignored local workspace)",
    )
    parser.add_argument("--package", help="optional source package provenance label")
    parser.add_argument("--name", help="style name for a Pa80 export directory")
    parser.add_argument(
        "--id",
        help="stable korg-lowercase-slug id (useful when groups repeat names)",
    )
    parser.add_argument(
        "--group",
        help="explicit arranger library group for a Pa80 export directory",
    )
    parser.add_argument(
        "--source-file",
        help="original style bank provenance for a Pa80 export directory",
    )
    parser.add_argument("--debug", action="store_true", help="print all diagnostics")
    parser.add_argument("--dump-markers", action="store_true")
    parser.add_argument("--dump-tracks", action="store_true")
    parser.add_argument("--dump-sysex", action="store_true")
    parser.add_argument("--dump-events", action="store_true")
    return parser


def main() -> int:
    """Import one MIDI file, report its sections, and write readable JSON."""

    arguments = build_parser().parse_args()
    try:
        if arguments.input.is_dir():
            pa80_result = inspect_pa80_smf_directory(
                arguments.input,
                style_name=arguments.name,
                original_file=arguments.source_file,
                package=arguments.package,
                style_id=arguments.id,
                library_group=arguments.group,
            )
            style = pa80_result.style
            format_description = "Pa80 Style to MIDI 1.06 Chord Variation set"
            diagnostics = pa80_diagnostics_to_dict(pa80_result.diagnostics)
        else:
            midi_result = inspect_korg_midi_style(
                arguments.input, package=arguments.package
            )
            style = midi_result.style
            format_description = (
                "marker-based Standard MIDI File (origin not authenticated)"
            )
            diagnostics = diagnostics_to_dict(midi_result.diagnostics)
    except (OSError, UnsupportedKorgStyleFormat) as error:
        build_parser().error(str(error))
    repository = Path(__file__).resolve().parents[1]
    output_directory = arguments.output or (
        repository / "assets/styles/korg/converted" / style.id
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / "style.json"
    output_path.write_text(
        json.dumps(style_to_dict(style), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    tempo = (
        f"{style.tempo_bpm:.2f} BPM" if style.tempo_bpm is not None else "not declared"
    )
    meter = (
        f"{style.time_signature[0]}/{style.time_signature[1]}"
        if style.time_signature is not None
        else "not declared"
    )
    print("Detected:")
    print(f"  Format: {format_description}")
    print(f"  Tempo: {tempo}")
    print(f"  Meter: {meter}")
    print("Elements:")
    for element in style.elements:
        event_count = sum(
            len(track.events)
            for variation in element.chord_variations
            for track in variation.tracks
        )
        print(
            f"  {element.name}: {len(element.chord_variations)} chord variation(s), "
            f"{event_count} events"
        )
    print(f"Converted successfully:\n  {output_path}")

    if arguments.debug:
        _dump("Diagnostics", diagnostics)
    else:
        if arguments.dump_markers:
            _dump("Markers", diagnostics.get("markers", []))
        if arguments.dump_tracks:
            _dump("Tracks", diagnostics.get("tracks", diagnostics.get("files", [])))
        if arguments.dump_sysex:
            tracks = diagnostics.get("tracks", [])
            assert isinstance(tracks, list)
            _dump(
                "SysEx counts",
                [
                    {
                        "track": track.get("name", "unknown"),
                        "count": track.get("sysex_count", 0),
                    }
                    for track in tracks
                    if isinstance(track, dict)
                ],
            )
        if arguments.dump_events:
            _dump("Style events", style_to_dict(style)["elements"])
    return 0


def _dump(label: str, value: Any) -> None:
    print(f"{label}:")
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
