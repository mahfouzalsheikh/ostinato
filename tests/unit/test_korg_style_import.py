from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast

import mido  # type: ignore[import-untyped]

from ostinato.styles.importers.korg.markers import (
    normalize_korg_marker,
    normalize_korg_track_role,
)
from ostinato.styles.importers.korg.midi_style_importer import (
    UnsupportedKorgStyleFormat,
    inspect_korg_midi_style,
)
from ostinato.styles.importers.korg.pa80_smf import inspect_pa80_smf_directory
from ostinato.styles.models import (
    ControlChangeEvent,
    JsonValue,
    NoteEvent,
    PitchBendEvent,
    ProgramChangeEvent,
    StyleElementType,
    StyleTrackRole,
    style_to_dict,
)


class KorgMarkerTests(unittest.TestCase):
    def test_normalizes_section_aliases_and_chord_variations(self) -> None:
        cases = {
            "V1-CV2": (StyleElementType.VARIATION_1, 2),
            "Variation 4 Chord Variation 6": (StyleElementType.VARIATION_4, 6),
            "Intro:3 CV1": (StyleElementType.INTRO_3, 1),
            "FILL_2": (StyleElementType.FILL_2, None),
            "End 1 - CV 2": (StyleElementType.ENDING_1, 2),
            "Break CV1": (StyleElementType.BREAK, 1),
        }

        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                descriptor = normalize_korg_marker(raw)
                self.assertIsNotNone(descriptor)
                assert descriptor is not None
                self.assertEqual(
                    (descriptor.element_type, descriptor.chord_variation), expected
                )

    def test_leaves_unknown_or_out_of_range_markers_unknown(self) -> None:
        self.assertIsNone(normalize_korg_marker("Vamp 1"))
        self.assertIsNone(normalize_korg_marker("Intro 4 CV1"))
        self.assertIsNone(normalize_korg_marker("V1-CV2 extra"))

    def test_track_roles_require_explicit_names(self) -> None:
        self.assertEqual(normalize_korg_track_role("Drums"), StyleTrackRole.DRUM)
        self.assertEqual(
            normalize_korg_track_role("Accompaniment 5"), StyleTrackRole.ACC5
        )
        self.assertEqual(
            normalize_korg_track_role("Channel 10"), StyleTrackRole.UNKNOWN
        )


class KorgMidiStyleImporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "Synthetic Ballad.mid"
        _write_synthetic_style(self.path)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_imports_sections_tracks_events_tempo_and_meter(self) -> None:
        result = inspect_korg_midi_style(self.path, package="synthetic-test")
        style = result.style

        self.assertEqual(style.id, "korg-synthetic-ballad")
        self.assertEqual(style.tempo_microseconds_per_beat, 750_000)
        self.assertEqual(style.tempo_bpm, 80.0)
        self.assertEqual(style.time_signature, (4, 4))
        self.assertEqual(
            [element.type for element in style.elements],
            [StyleElementType.VARIATION_1, StyleElementType.FILL_1],
        )
        variation, fill = style.elements
        self.assertEqual(variation.chord_variations[0].number, 1)
        self.assertEqual(variation.chord_variations[0].length_ticks, 1920)
        self.assertEqual(fill.chord_variations[0].length_ticks, 240)
        self.assertEqual(style.metadata["unknown_markers"], ["Author note"])
        self.assertEqual(style.metadata["source_chord_status"], "unknown")

        tracks = variation.chord_variations[0].tracks
        bass = next(track for track in tracks if track.role is StyleTrackRole.BASS)
        drums = next(track for track in tracks if track.role is StyleTrackRole.DRUM)
        self.assertEqual((bass.bank_msb, bass.bank_lsb, bass.program), (1, 2, 32))
        self.assertTrue(any(isinstance(event, NoteEvent) for event in bass.events))
        self.assertTrue(
            any(isinstance(event, ControlChangeEvent) for event in bass.events)
        )
        self.assertTrue(
            any(isinstance(event, ProgramChangeEvent) for event in bass.events)
        )
        self.assertEqual(bass.metadata["clipped_note_count"], 0)
        self.assertEqual(drums.midi_channel, 9)
        self.assertEqual(drums.role, StyleTrackRole.DRUM)
        fill_bass = next(
            track
            for track in fill.chord_variations[0].tracks
            if track.role is StyleTrackRole.BASS
        )
        self.assertEqual(
            (fill_bass.bank_msb, fill_bass.bank_lsb, fill_bass.program),
            (1, 2, 32),
        )

    def test_preserves_unknown_track_role_and_detailed_diagnostics(self) -> None:
        result = inspect_korg_midi_style(self.path)
        variation = result.style.elements[0].chord_variations[0]
        piano = next(
            track for track in variation.tracks if track.source_name == "Piano"
        )

        self.assertEqual(piano.role, StyleTrackRole.UNKNOWN)
        self.assertEqual(result.diagnostics.midi_format, 1)
        self.assertEqual(result.diagnostics.track_count, 4)
        self.assertEqual(result.diagnostics.tracks[2].note_range, (36, 38))

    def test_serialized_model_keeps_integer_ticks_and_source_provenance(self) -> None:
        document = style_to_dict(inspect_korg_midi_style(self.path).style)
        source = cast(dict[str, JsonValue], document["source"])
        elements = cast(list[JsonValue], document["elements"])
        first_element = cast(dict[str, JsonValue], elements[0])
        variations = cast(list[JsonValue], first_element["chord_variations"])
        variation = cast(dict[str, JsonValue], variations[0])

        self.assertEqual(document["ticks_per_beat"], 480)
        self.assertEqual(source["manufacturer"], "KORG")
        self.assertIsInstance(variation["length_ticks"], int)

    def test_rejects_opaque_sty_and_unmarked_midi_gracefully(self) -> None:
        sty_path = Path(self.temporary.name) / "opaque.STY"
        sty_path.write_bytes(b"not midi")
        unmarked_path = Path(self.temporary.name) / "unmarked.mid"
        midi = mido.MidiFile(type=0, ticks_per_beat=480)
        midi.tracks.append(mido.MidiTrack())
        midi.save(unmarked_path)

        with self.assertRaisesRegex(
            UnsupportedKorgStyleFormat, "native .STY parsing is not supported"
        ):
            inspect_korg_midi_style(sty_path)
        with self.assertRaisesRegex(
            UnsupportedKorgStyleFormat, "no recognized KORG style section markers"
        ):
            inspect_korg_midi_style(unmarked_path)

    def test_import_cli_writes_readable_style_json_and_diagnostics(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        output = Path(self.temporary.name) / "converted"
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(repository / "src")

        completed = subprocess.run(
            [
                sys.executable,
                "scripts/import_korg_style.py",
                str(self.path),
                "--output",
                str(output),
                "--dump-markers",
            ],
            cwd=repository,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Variation 1: 1 chord variation(s)", completed.stdout)
        self.assertIn("origin not authenticated", completed.stdout)
        document = json.loads((output / "style.json").read_text(encoding="utf-8"))
        self.assertEqual(document["elements"][0]["type"], "variation_1")


class Pa80ChordVariationImporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "sweet-ballad"
        self.path.mkdir()
        _write_pa80_variation(self.path / "v1cv1.mid", include_pitch_bend=True)
        _write_pa80_variation(self.path / "f1cv1.mid")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_imports_standard_filenames_and_official_channel_roles(self) -> None:
        result = inspect_pa80_smf_directory(
            self.path,
            style_name="SweetBallad",
            original_file="USER01.STY#1",
            package="Styl-v01.zip",
        )
        style = result.style

        self.assertEqual(style.id, "korg-sweetballad")
        self.assertEqual(style.ticks_per_beat, 384)
        self.assertEqual(style.time_signature, (4, 4))
        self.assertEqual(style.tempo_microseconds_per_beat, 500_000)
        self.assertEqual(
            [element.type for element in style.elements],
            [StyleElementType.VARIATION_1, StyleElementType.FILL_1],
        )
        variation = style.elements[0].chord_variations[0]
        self.assertEqual(variation.number, 1)
        self.assertEqual(variation.length_ticks, 384)
        self.assertEqual(variation.source_chord, None)
        self.assertEqual(
            [track.role for track in variation.tracks],
            [StyleTrackRole.BASS, StyleTrackRole.DRUM],
        )
        bass = variation.tracks[0]
        self.assertEqual((bass.bank_msb, bass.bank_lsb, bass.program), (121, 3, 33))
        self.assertTrue(any(isinstance(event, PitchBendEvent) for event in bass.events))
        self.assertEqual(
            style.metadata["origin_authentication"],
            "not_authenticated_by_file_format",
        )
        self.assertEqual(
            style.metadata["format_profile"],
            "official_korg_pa80_style_to_midi_1.06",
        )
        self.assertEqual(style.metadata["source_chord_status"], "not_present_in_smf")
        self.assertEqual(result.diagnostics.files[0].filename, "v1cv1.mid")

    def test_accepts_stable_group_qualified_id_and_library_group(self) -> None:
        result = inspect_pa80_smf_directory(
            self.path,
            style_name="SweetBallad",
            style_id="korg-v01-sweetballad",
            library_group="KORG Styles · Volume 1",
        )

        self.assertEqual(result.style.id, "korg-v01-sweetballad")
        self.assertEqual(
            result.style.metadata["library_group"], "KORG Styles · Volume 1"
        )

        with self.assertRaisesRegex(UnsupportedKorgStyleFormat, "style id"):
            inspect_pa80_smf_directory(self.path, style_id="unsafe id")
        with self.assertRaisesRegex(UnsupportedKorgStyleFormat, "library group"):
            inspect_pa80_smf_directory(self.path, library_group="  ")

    def test_rejects_nonstandard_names_and_inconsistent_resolution(self) -> None:
        bad_name = Path(self.temporary.name) / "bad-name"
        bad_name.mkdir()
        _write_pa80_variation(bad_name / "V1CV1.mid")
        with self.assertRaisesRegex(
            UnsupportedKorgStyleFormat, "lowercase EnCVn convention"
        ):
            inspect_pa80_smf_directory(bad_name)

        inconsistent = Path(self.temporary.name) / "inconsistent"
        inconsistent.mkdir()
        _write_pa80_variation(inconsistent / "v1cv1.mid", ticks_per_beat=384)
        _write_pa80_variation(inconsistent / "f1cv1.mid", ticks_per_beat=480)
        with self.assertRaisesRegex(UnsupportedKorgStyleFormat, "tick resolutions"):
            inspect_pa80_smf_directory(inconsistent)

    def test_cli_imports_a_pa80_chord_variation_directory(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        output = Path(self.temporary.name) / "converted"
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(repository / "src")

        completed = subprocess.run(
            [
                sys.executable,
                "scripts/import_korg_style.py",
                str(self.path),
                "--name",
                "SweetBallad",
                "--source-file",
                "USER01.STY#1",
                "--package",
                "Styl-v01.zip",
                "--output",
                str(output),
                "--dump-tracks",
            ],
            cwd=repository,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Pa80 Style to MIDI 1.06", completed.stdout)
        self.assertIn("Variation 1: 1 chord variation(s)", completed.stdout)
        document = json.loads((output / "style.json").read_text(encoding="utf-8"))
        self.assertEqual(
            document["source"]["source_format"],
            "pa80_style_to_midi_1.06_chord_variations",
        )
        events = document["elements"][0]["chord_variations"][0]["tracks"][0]["events"]
        self.assertTrue(
            any(event["type"] == "pitch_bend" for event in events),
        )


def _write_synthetic_style(path: Path) -> None:
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    conductor = mido.MidiTrack()
    conductor.append(mido.MetaMessage("track_name", name="Conductor", time=0))
    conductor.append(mido.MetaMessage("set_tempo", tempo=750_000, time=0))
    conductor.append(
        mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0)
    )
    conductor.append(mido.MetaMessage("marker", text="V1-CV1", time=0))
    conductor.append(mido.MetaMessage("marker", text="Author note", time=960))
    conductor.append(mido.MetaMessage("marker", text="Fill 1 CV1", time=960))
    midi.tracks.append(conductor)

    drums = mido.MidiTrack()
    drums.append(mido.MetaMessage("track_name", name="Drums", time=0))
    drums.append(mido.Message("note_on", channel=9, note=36, velocity=100, time=0))
    drums.append(mido.Message("note_off", channel=9, note=36, velocity=0, time=120))
    drums.append(mido.Message("note_on", channel=9, note=38, velocity=96, time=1800))
    drums.append(mido.Message("note_off", channel=9, note=38, velocity=0, time=240))
    midi.tracks.append(drums)

    bass = mido.MidiTrack()
    bass.append(mido.MetaMessage("track_name", name="Bass", time=0))
    bass.append(mido.Message("control_change", channel=1, control=0, value=1, time=0))
    bass.append(mido.Message("control_change", channel=1, control=32, value=2, time=0))
    bass.append(mido.Message("program_change", channel=1, program=32, time=0))
    bass.append(mido.Message("note_on", channel=1, note=36, velocity=88, time=0))
    bass.append(mido.Message("note_off", channel=1, note=36, velocity=0, time=480))
    bass.append(mido.Message("note_on", channel=1, note=38, velocity=82, time=1440))
    bass.append(mido.Message("note_off", channel=1, note=38, velocity=0, time=240))
    midi.tracks.append(bass)

    piano = mido.MidiTrack()
    piano.append(mido.MetaMessage("track_name", name="Piano", time=0))
    piano.append(mido.Message("note_on", channel=2, note=60, velocity=72, time=0))
    piano.append(mido.Message("note_off", channel=2, note=60, velocity=0, time=480))
    piano.append(mido.Message("note_on", channel=2, note=62, velocity=72, time=1440))
    piano.append(mido.Message("note_off", channel=2, note=62, velocity=0, time=240))
    midi.tracks.append(piano)
    midi.save(path)


def _write_pa80_variation(
    path: Path,
    *,
    ticks_per_beat: int = 384,
    include_pitch_bend: bool = False,
) -> None:
    midi = mido.MidiFile(type=0, ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("set_tempo", tempo=500_000, time=0))
    track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    track.append(
        mido.Message("control_change", channel=8, control=11, value=96, time=0)
    )
    track.append(
        mido.Message("control_change", channel=8, control=0, value=121, time=0)
    )
    track.append(mido.Message("control_change", channel=8, control=32, value=3, time=0))
    track.append(mido.Message("program_change", channel=8, program=33, time=0))
    track.append(mido.Message("note_on", channel=8, note=36, velocity=90, time=0))
    track.append(mido.Message("note_on", channel=9, note=36, velocity=100, time=0))
    if include_pitch_bend:
        track.append(mido.Message("pitchwheel", channel=8, pitch=128, time=96))
        remaining = ticks_per_beat - 96
    else:
        remaining = ticks_per_beat
    track.append(
        mido.Message("note_on", channel=8, note=36, velocity=0, time=remaining)
    )
    track.append(mido.Message("note_on", channel=9, note=36, velocity=0, time=0))
    midi.tracks.append(track)
    midi.save(path)


if __name__ == "__main__":
    unittest.main()
