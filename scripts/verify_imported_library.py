#!/usr/bin/env python3
"""Render each imported live section to memory without opening an audio device."""

from __future__ import annotations

import argparse
import array
import json
import os
from dataclasses import replace
from pathlib import Path

from ostinato.computer_audio import DemoAudioConfig
from ostinato.domain import ChordQuality, ChordState
from ostinato.styles.controls import StyleControls
from ostinato.styles.library import ImportedStyleLibrary
from ostinato.styles.live_audio import (
    ImportedStyleArrangementRenderer,
    imported_style_playback_info,
)
from ostinato.styles.models import NoteEvent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path)
    parser.add_argument("--soundfont", default=os.environ.get("OSTINATO_SOUNDFONT"))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.soundfont:
        parser.error("provide the exact configured SoundFont path")
    config = DemoAudioConfig(tempo_bpm=120, sample_rate=48_000)
    chord = ChordState(0, ChordQuality.MAJOR, None, 1.0, ("software verification",), 0)
    results = []
    failed = False
    for style in ImportedStyleLibrary(args.library).load():
        info = imported_style_playback_info(style)
        renderer = ImportedStyleArrangementRenderer(style, config, args.soundfont)
        try:
            for element in style.elements:
                name = element.type.value
                pattern = info.sections.get(name)
                if pattern is None:
                    continue
                controls = StyleControls()
                kind, number = name.rsplit("_", 1)
                renderer.stop()
                if kind == "variation":
                    controls = replace(controls, variation=int(number))
                elif kind == "intro":
                    controls = replace(controls, intro=int(number))
                elif kind == "ending":
                    controls = replace(controls, ending=int(number))
                renderer.configure_style_controls(controls)
                if kind == "intro":
                    renderer.start_intro()
                else:
                    renderer.start_main()
                if kind in ("ending", "fill"):
                    if kind == "ending":
                        renderer.request_ending()
                    else:
                        renderer.request_fill(int(number))
                    renderer.render(info.beats_per_bar * config.sample_rate // 2, chord)
                notes = [
                    event
                    for track in pattern.tracks
                    for event in track.events
                    if isinstance(event, NoteEvent)
                ]
                first_tick = min((event.start_tick for event in notes), default=0)
                frames = config.sample_rate + (
                    first_tick * config.sample_rate // (2 * style.ticks_per_beat)
                )
                pcm = renderer.render(frames, chord)
                samples = array.array("h", pcm)
                peak = max((abs(sample) for sample in samples), default=0)
                valid = len(pcm) == frames * 4 and (peak > 0 or not notes)
                failed |= not valid
                results.append(
                    {
                        "style": style.id,
                        "section": name,
                        "frames": frames,
                        "peak": peak,
                        "has_source_notes": bool(notes),
                        "valid": valid,
                    }
                )
            print(style.id, "rendered", flush=True)
        finally:
            renderer.close()
    args.report.write_text(
        json.dumps(
            {"hardware_exercised": False, "sections": results, "passed": not failed},
            indent=2,
        )
        + "\n"
    )
    print(f"{len(results)} sections; passed={not failed}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
