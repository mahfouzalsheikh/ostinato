from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from ostinato.computer_audio import DemoAudioConfig, DemoSection
from ostinato.domain import ChordQuality, ChordState
from ostinato.style_timeline import imported_style_timeline
from ostinato.styles.library import ImportedStyleLibrary, ImportedStyleLibraryError
from ostinato.styles.live_audio import (
    ImportedStyleArrangementRenderer,
    imported_style_playback_info,
)
from ostinato.styles.models import (
    ChordVariation,
    NoteEvent,
    ProgramChangeEvent,
    Style,
    StyleElement,
    StyleElementType,
    StyleSource,
    StyleTrack,
    StyleTrackRole,
    style_to_dict,
)


class FakeSynth:
    def __init__(self) -> None:
        self.frame = 0
        self.programs: list[tuple[int, int, int, int]] = []
        self.controls: list[tuple[int, int, int, int]] = []
        self.pitch_bends: list[tuple[int, int, int]] = []
        self.note_ons: list[tuple[int, int, int, int]] = []
        self.note_offs: list[tuple[int, int, int]] = []
        self.closed = False

    def program_select(self, channel: int, bank: int, program: int) -> None:
        self.programs.append((self.frame, channel, bank, program))

    def control_change(self, channel: int, controller: int, value: int) -> None:
        self.controls.append((self.frame, channel, controller, value))

    def pitch_bend(self, channel: int, value: int) -> None:
        self.pitch_bends.append((self.frame, channel, value))

    def set_gain(self, gain: float) -> None:
        pass

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self.note_ons.append((self.frame, channel, note, velocity))

    def note_off(self, channel: int, note: int) -> None:
        self.note_offs.append((self.frame, channel, note))

    def render(self, frame_count: int) -> bytes:
        self.frame += frame_count
        return bytes(frame_count * 4)

    def close(self) -> None:
        self.closed = True


class ImportedStyleLibraryTests(unittest.TestCase):
    def test_round_trips_a_valid_local_document_and_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            style_path = root / "test" / "style.json"
            style_path.parent.mkdir()
            style_path.write_text(json.dumps(style_to_dict(_style())), encoding="utf-8")

            loaded = ImportedStyleLibrary(root).load()
            self.assertEqual(loaded, (_style(),))

            style_path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ImportedStyleLibraryError, "version"):
                ImportedStyleLibrary(root).load()

    def test_timeline_exposes_the_exact_main_cv1_phrase(self) -> None:
        timeline = imported_style_timeline(_style())

        self.assertEqual(timeline["beats_per_bar"], 2)
        self.assertEqual(timeline["phrase_bars"], 1)
        self.assertEqual(
            [lane["id"] for lane in timeline["lanes"]],
            ["bass", "comp", "fill", "backing", "drums"],
        )
        self.assertEqual(len(timeline["lanes"][0]["events"]), 2)
        self.assertEqual(
            timeline["playback_policy"], "Variation 1 CV1 · Ostinato chord adaptation"
        )

    def test_uses_a_melodic_fallback_anchor_when_main_has_no_bass(self) -> None:
        style = _style()
        main = style.elements[0]
        variation = main.chord_variations[0]
        tracks_without_bass = tuple(
            track for track in variation.tracks if track.role is not StyleTrackRole.BASS
        )
        imported = replace(
            style,
            elements=(
                replace(
                    main,
                    chord_variations=(replace(variation, tracks=tracks_without_bass),),
                ),
                *style.elements[1:],
            ),
        )

        info = imported_style_playback_info(imported)

        self.assertEqual(info.anchor_pitch_class, 4)


class ImportedStyleArrangementRendererTests(unittest.TestCase):
    def setUp(self) -> None:
        self.synth = FakeSynth()
        self.renderer = ImportedStyleArrangementRenderer(
            _style(),
            DemoAudioConfig(tempo_bpm=120, sample_rate=1_000, chunk_frames=10),
            "/configured/test.sf2",
            engine_factory=lambda _config, _path: self.synth,
        )
        self.c_minor = ChordState(0, ChordQuality.MINOR, None, 1.0, ("test",), 0)

    def tearDown(self) -> None:
        self.renderer.close()

    def test_adapts_melodic_chord_tones_but_preserves_percussion_notes(self) -> None:
        self.renderer.render(100, self.c_minor)

        sounding = {(channel, note) for _, channel, note, _ in self.synth.note_ons}
        self.assertIn((8, 36), sounding)
        self.assertIn((11, 63), sounding)  # source E becomes Eb for C minor
        self.assertIn((9, 36), sounding)  # percussion pitch is unchanged
        self.assertIn((0, 8, 0, 33), self.synth.programs)
        self.assertIn((0, 9, 128, 0), self.synth.programs)
        drum_programs = [
            program for _, channel, _, program in self.synth.programs if channel == 9
        ]
        self.assertNotIn(66, drum_programs)

    def test_main_pattern_loops_at_its_exact_source_length(self) -> None:
        self.renderer.render(1_100, self.c_minor)

        bass_starts = [
            frame
            for frame, channel, note, _ in self.synth.note_ons
            if channel == 8 and note == 36
        ]
        self.assertEqual(bass_starts[:3], [0, 500, 1_000])

    def test_intro_fill_and_ending_use_their_source_cv1_sections(self) -> None:
        self.renderer.start_intro()
        self.renderer.render(600, self.c_minor)
        self.assertEqual(self.renderer.section, DemoSection.MAIN)
        self.assertIn((0, 11, 60, 80), self.synth.note_ons)
        self.assertIn((500, 11, 63, 80), self.synth.note_ons)

        self.renderer.request_fill(1)
        self.renderer.render(1_500, self.c_minor)
        self.assertIn((1_000, 11, 65, 92), self.synth.note_ons)
        self.assertIsNone(self.renderer.fill_variation)

        self.renderer.request_ending()
        self.renderer.render(1_500, self.c_minor)
        self.assertEqual(self.renderer.section, DemoSection.STOPPED)
        self.assertTrue(
            any(
                note == 67
                for _, channel, note, _ in self.synth.note_ons
                if channel == 11
            )
        )


def _style() -> Style:
    sections = (
        _element(StyleElementType.VARIATION_1, 192, ((0, 36, 90), (96, 36, 88)), 64),
        _element(StyleElementType.INTRO_1, 96, ((0, 36, 70),), 60),
        _element(StyleElementType.FILL_1, 192, ((0, 36, 94),), 65),
        _element(StyleElementType.FILL_2, 192, ((0, 36, 96),), 66),
        _element(StyleElementType.ENDING_1, 96, ((0, 36, 84),), 67),
    )
    return Style(
        version=1,
        id="korg-test",
        name="KORG test",
        source=StyleSource("KORG", "Pa80 Style To Midi", "test.STY"),
        ticks_per_beat=96,
        tempo_microseconds_per_beat=500_000,
        time_signature=(2, 4),
        elements=sections,
    )


def _element(
    element_type: StyleElementType,
    length: int,
    bass_notes: tuple[tuple[int, int, int], ...],
    accompaniment_note: int,
) -> StyleElement:
    bass = StyleTrack(
        StyleTrackRole.BASS,
        "Bass",
        8,
        33,
        121,
        3,
        tuple(
            NoteEvent(tick, 48, note, velocity, 8)
            for tick, note, velocity in bass_notes
        ),
    )
    accompaniment = StyleTrack(
        StyleTrackRole.ACC1,
        "Acc1",
        11,
        0,
        121,
        0,
        (
            NoteEvent(
                0,
                48,
                accompaniment_note,
                80 if element_type is not StyleElementType.FILL_1 else 92,
                11,
            ),
        ),
    )
    drums = StyleTrack(
        StyleTrackRole.DRUM,
        "Drum",
        9,
        0,
        120,
        0,
        (NoteEvent(0, 24, 36, 100, 9), ProgramChangeEvent(12, 66, 9)),
    )
    return StyleElement(
        element_type,
        element_type.value,
        (ChordVariation(1, None, length, (bass, accompaniment, drums)),),
    )


if __name__ == "__main__":
    unittest.main()


def expanded_style() -> Style:
    style = _style()
    return replace(
        style,
        elements=(
            *style.elements,
            _element(StyleElementType.VARIATION_2, 384, ((0, 36, 90),), 69),
            _element(StyleElementType.VARIATION_3, 192, ((0, 36, 90),), 72),
            _element(StyleElementType.VARIATION_4, 192, ((0, 36, 90),), 76),
            _element(StyleElementType.INTRO_2, 192, ((0, 36, 90),), 74),
            _element(StyleElementType.ENDING_2, 192, ((0, 36, 90),), 77),
        ),
    )


class ExpandedStyleTests(unittest.TestCase):
    def setUp(self) -> None:
        from ostinato.styles.controls import StyleControls

        self.controls = StyleControls()
        self.synth = FakeSynth()
        self.renderer = ImportedStyleArrangementRenderer(
            expanded_style(),
            DemoAudioConfig(tempo_bpm=120, sample_rate=1_000, chunk_frames=10),
            "/configured/test.sf2",
            engine_factory=lambda _config, _path: self.synth,
        )
        self.chord = ChordState(0, ChordQuality.MAJOR, None, 1.0, ("test",), 0)

    def tearDown(self) -> None:
        self.renderer.close()

    def test_switches_variation_at_next_bar_and_restarts_new_phrase(self) -> None:
        self.renderer.render(250, self.chord)
        self.renderer.configure_style_controls(replace(self.controls, variation=2))
        self.renderer.render(749, self.chord)
        self.assertEqual(self.renderer.main_variation, 1)
        self.renderer.render(2, self.chord)
        self.assertEqual(self.renderer.main_variation, 2)
        self.assertIn((1000, 11, 69, 80), self.synth.note_ons)
        self.renderer.render(2000, self.chord)
        self.assertIn((3000, 11, 69, 80), self.synth.note_ons)

    def test_selected_intro_and_ending_keep_their_full_source_lengths(self) -> None:
        self.renderer.configure_style_controls(
            replace(self.controls, variation=3, intro=2, ending=2)
        )
        self.renderer.start_intro()
        self.renderer.render(1001, self.chord)
        self.assertIn((0, 11, 74, 80), self.synth.note_ons)
        self.assertIn((1000, 11, 72, 80), self.synth.note_ons)
        self.renderer.request_ending()
        self.renderer.render(1500, self.chord)
        self.assertEqual(self.renderer.section, DemoSection.ENDING)
        self.assertIn((2000, 11, 77, 80), self.synth.note_ons)
        self.renderer.render(500, self.chord)
        self.assertEqual(self.renderer.section, DemoSection.STOPPED)

    def test_mix_silences_active_notes_and_solo_preserves_only_selected_role(
        self,
    ) -> None:
        self.renderer.render(100, self.chord)
        self.renderer.configure_style_controls(
            self.controls.update_track({"role": "bass", "muted": True})
        )
        self.assertIn((100, 8, 120, 0), self.synth.controls)
        self.renderer.render(500, self.chord)
        self.assertFalse(
            any(
                frame >= 100 and channel == 8
                for frame, channel, _, _ in self.synth.note_ons
            )
        )
        self.renderer.configure_style_controls(
            self.controls.update_track({"role": "drum", "solo": True})
        )
        self.renderer.render(1500, self.chord)
        self.assertTrue(
            all(
                channel == 9
                for frame, channel, _, _ in self.synth.note_ons
                if frame >= 600
            )
        )

    def test_tempo_change_retimes_queued_note_off(self) -> None:
        self.renderer.render(100, self.chord)
        self.renderer.set_tempo(60)
        self.renderer.render(301, self.chord)
        self.assertIn((400, 8, 36), self.synth.note_offs)

    def test_unavailable_sections_are_rejected_before_state_changes(self) -> None:
        renderer = ImportedStyleArrangementRenderer(
            _style(),
            DemoAudioConfig(),
            "/configured/test.sf2",
            engine_factory=lambda _config, _path: FakeSynth(),
        )
        with self.assertRaisesRegex(ValueError, "no variation 4"):
            renderer.configure_style_controls(replace(self.controls, variation=4))
        self.assertEqual(renderer.main_variation, 1)
        renderer.close()

    def test_timeline_returns_selected_section(self) -> None:
        timeline = imported_style_timeline(expanded_style(), section="variation_2")
        self.assertEqual(timeline["total_beats"], 4)
        self.assertEqual(timeline["section"], "variation_2")
        with self.assertRaises(ValueError):
            imported_style_timeline(expanded_style(), section="intro_3")


def test_variation_request_waits_for_full_fill_without_cutting_it() -> None:
    from ostinato.styles.controls import StyleControls

    synth = FakeSynth()
    renderer = ImportedStyleArrangementRenderer(
        expanded_style(),
        DemoAudioConfig(tempo_bpm=120, sample_rate=1_000, chunk_frames=10),
        "/test.sf2",
        engine_factory=lambda _config, _path: synth,
    )
    chord = ChordState(0, ChordQuality.MAJOR, None, 1.0, ("test",), 0)
    renderer.render(100, chord)
    renderer.request_fill(1)
    renderer.configure_style_controls(StyleControls(variation=2))
    renderer.render(1001, chord)
    assert renderer.main_variation == 1
    assert (1000, 11, 65, 92) in synth.note_ons
    renderer.render(900, chord)
    assert renderer.main_variation == 2
    assert (2000, 11, 69, 80) in synth.note_ons
    renderer.close()


def test_volume_scales_source_controller_and_survives_section_changes() -> None:
    from ostinato.styles.controls import StyleControls
    from ostinato.styles.models import ControlChangeEvent

    style = expanded_style()
    main = style.elements[0]
    cv = main.chord_variations[0]
    bass = cv.tracks[0]
    bass = replace(bass, events=(ControlChangeEvent(0, 7, 80, 8), *bass.events))
    style = replace(
        style,
        elements=(
            replace(
                main, chord_variations=(replace(cv, tracks=(bass, *cv.tracks[1:])),)
            ),
            *style.elements[1:],
        ),
    )
    synth = FakeSynth()
    renderer = ImportedStyleArrangementRenderer(
        style,
        DemoAudioConfig(tempo_bpm=120, sample_rate=1_000, chunk_frames=10),
        "/test.sf2",
        engine_factory=lambda _config, _path: synth,
    )
    controls = StyleControls().update_track({"role": "bass", "volume": 50})
    renderer.configure_style_controls(controls)
    chord = ChordState(0, ChordQuality.MAJOR, None, 1.0, ("test",), 0)
    renderer.render(100, chord)
    assert (0, 8, 7, 40) in synth.controls
    renderer.configure_style_controls(replace(controls, variation=2))
    assert (100, 8, 7, 40) in synth.controls
    renderer.close()


def test_tempo_following_uses_the_selected_main_variation_rhythm() -> None:
    from ostinato.styles.live_audio import imported_style_rhythm_spans

    style = expanded_style()
    assert 4.0 not in imported_style_rhythm_spans(style, variation_number=1)
    assert 4.0 in imported_style_rhythm_spans(style, variation_number=2)
