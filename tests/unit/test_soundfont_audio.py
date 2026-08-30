from __future__ import annotations

import unittest

from ostinato.computer_audio import (
    DEMO_STYLES,
    TRANSPORT_TICKS_PER_BEAT,
    DemoAudioConfig,
    DemoSection,
)
from ostinato.domain import ChordQuality, ChordState
from ostinato.soundfont_audio import (
    DRUM_CHANNEL,
    PALETTES,
    SoundFontArrangementRenderer,
)
from ostinato.style_designer import CustomStyle, default_custom_style_payload


class FakeSynthEngine:
    def __init__(self) -> None:
        self.programs: list[tuple[int, int, int]] = []
        self.controls: list[tuple[int, int, int]] = []
        self.gains: list[float] = []
        self.note_ons: list[tuple[int, int, int]] = []
        self.note_offs: list[tuple[int, int]] = []
        self.rendered_frames = 0
        self.closed = False

    def program_select(self, channel: int, bank: int, program: int) -> None:
        self.programs.append((channel, bank, program))

    def control_change(self, channel: int, controller: int, value: int) -> None:
        self.controls.append((channel, controller, value))

    def set_gain(self, gain: float) -> None:
        self.gains.append(gain)

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self.note_ons.append((channel, note, velocity))

    def note_off(self, channel: int, note: int) -> None:
        self.note_offs.append((channel, note))

    def render(self, frame_count: int) -> bytes:
        self.rendered_frames += frame_count
        return bytes(frame_count * 4)

    def close(self) -> None:
        self.closed = True


def chord(root: int = 0, quality: ChordQuality = ChordQuality.MAJOR) -> ChordState:
    return ChordState(root, quality, root, 1.0, ("test",), 0)


class SoundFontArrangementRendererTests(unittest.TestCase):
    def create_renderer(
        self,
        style_id: str = "modern_tango",
        *,
        tempo_bpm: int = 120,
        sample_rate: int = 1_000,
        custom_style: CustomStyle | None = None,
    ) -> tuple[SoundFontArrangementRenderer, FakeSynthEngine]:
        engine = FakeSynthEngine()
        renderer = SoundFontArrangementRenderer(
            style_id,
            DemoAudioConfig(
                tempo_bpm=tempo_bpm,
                sample_rate=sample_rate,
                chunk_frames=10,
            ),
            "/configured/test.sf2",
            custom_style=custom_style,
            engine_factory=lambda _config, _path: engine,
        )
        return renderer, engine

    def test_palette_configures_four_instruments_and_gm_drums(self) -> None:
        _, engine = self.create_renderer("bossa_nova")

        self.assertEqual(len(engine.programs), 5)
        self.assertIn((1, 0, 25), engine.programs)
        self.assertIn((DRUM_CHANNEL, 128, 0), engine.programs)
        self.assertEqual(engine.gains, [1.9])

    def test_built_in_palettes_use_piano_guitar_flute_and_no_strings(self) -> None:
        for style_id, palette in PALETTES.items():
            with self.subTest(style=style_id):
                self.assertEqual(palette.bass_program, 25)
                self.assertIn(palette.comp_program, (0, 25))
                self.assertEqual(palette.reed_program, 73)
                self.assertEqual(palette.pad_program, 25)
                self.assertNotIn(
                    48,
                    (
                        palette.bass_program,
                        palette.comp_program,
                        palette.reed_program,
                        palette.pad_program,
                    ),
                )

    def test_custom_palette_and_muted_layers_are_applied(self) -> None:
        value = default_custom_style_payload()
        value["id"] = "custom-123456abcdef"
        value["comp"] = {"instrument": "acoustic_guitar", "volume": 75}
        value["backing"] = {"instrument": "none", "volume": 0}
        value["drums_enabled"] = False
        style = CustomStyle.from_mapping(value)
        renderer, engine = self.create_renderer(
            tempo_bpm=60, sample_rate=100, custom_style=style
        )

        renderer.render(400, chord())

        channels = {channel for channel, _note, _velocity in engine.note_ons}
        self.assertIn((1, 0, 25), engine.programs)
        self.assertNotIn(3, channels)
        self.assertNotIn(DRUM_CHANNEL, channels)

    def test_custom_instrument_register_and_phrase_length_are_applied(self) -> None:
        value = default_custom_style_payload()
        value["id"] = "custom-123456abcdef"
        value["phrase_bars"] = 1
        value["comp"] = {
            "instrument": "mandolin",
            "volume": 75,
            "octave": 1,
            "gate_percent": 55,
        }
        style = CustomStyle.from_mapping(value)
        renderer, engine = self.create_renderer(
            tempo_bpm=60, sample_rate=100, custom_style=style
        )

        renderer.render(800, chord())

        comp_notes = [
            note for channel, note, _velocity in engine.note_ons if channel == 1
        ]
        bass_notes = [
            note for channel, note, _velocity in engine.note_ons if channel == 0
        ]
        self.assertIn((1, 0, 25), engine.programs)
        self.assertGreaterEqual(min(comp_notes), 84)
        self.assertEqual(bass_notes[:3], bass_notes[3:6])

    def test_first_bar_uses_sampled_bass_harmony_and_drums(self) -> None:
        renderer, engine = self.create_renderer()

        pcm = renderer.render(300, chord())

        self.assertEqual(len(pcm), 1_200)
        self.assertEqual(engine.rendered_frames, 300)
        channels = {channel for channel, _note, _velocity in engine.note_ons}
        self.assertTrue({0, 1, 2, 3, DRUM_CHANNEL}.issubset(channels))

    def test_human_groove_pack_preserves_per_hit_drum_dynamics(self) -> None:
        renderer, engine = self.create_renderer(
            "funk_pocket", tempo_bpm=60, sample_rate=100
        )

        renderer.render(400, chord())

        kick_velocities = {
            velocity
            for channel, note, velocity in engine.note_ons
            if channel == DRUM_CHANNEL and note == 36
        }
        snare_velocities = {
            velocity
            for channel, note, velocity in engine.note_ons
            if channel == DRUM_CHANNEL and note == 38
        }
        self.assertGreater(len(kick_velocities), 1)
        self.assertGreater(len(snare_velocities), 1)

    def test_classic_tango_uses_acoustic_roles_without_a_drum_kit(self) -> None:
        renderer, engine = self.create_renderer(
            "classic_tango", tempo_bpm=60, sample_rate=100
        )

        renderer.render(400, chord())

        channels = {channel for channel, _note, _velocity in engine.note_ons}
        self.assertTrue({0, 1, 2, 3}.issubset(channels))
        self.assertNotIn(DRUM_CHANNEL, channels)

    def test_bossa_does_not_layer_generic_reed_and_string_parts(self) -> None:
        renderer, engine = self.create_renderer(
            "bossa_nova", tempo_bpm=60, sample_rate=100
        )

        renderer.render(400, chord())

        channels = {channel for channel, _note, _velocity in engine.note_ons}
        self.assertIn(0, channels)
        self.assertIn(1, channels)
        self.assertNotIn(2, channels)
        self.assertNotIn(3, channels)

    def test_swing_bass_third_follows_minor_quality(self) -> None:
        renderer, engine = self.create_renderer(
            "swing_foxtrot", tempo_bpm=60, sample_rate=100
        )

        renderer.render(400, chord(0, ChordQuality.MINOR))

        bass_notes = [
            note for channel, note, _velocity in engine.note_ons if channel == 0
        ]
        self.assertEqual(bass_notes[:4], [36, 39, 43, 48])

    def test_every_generated_pitch_stays_in_the_recognized_chord(self) -> None:
        intervals = {
            ChordQuality.MAJOR: (0, 4, 7),
            ChordQuality.MINOR: (0, 3, 7),
            ChordQuality.DOMINANT_SEVENTH: (0, 4, 7, 10),
            ChordQuality.DIMINISHED: (0, 3, 6),
        }
        for style_id, definition in DEMO_STYLES.items():
            for quality, chord_intervals in intervals.items():
                with self.subTest(style=style_id, quality=quality):
                    renderer, engine = self.create_renderer(
                        style_id, tempo_bpm=60, sample_rate=100
                    )
                    root = 8
                    renderer.render(
                        definition.beats_per_bar * 4 * 100,
                        chord(root, quality),
                    )
                    expected = {(root + interval) % 12 for interval in chord_intervals}
                    harmonic_notes = [
                        note
                        for channel, note, _velocity in engine.note_ons
                        if channel in (0, 1, 2, 3)
                    ]

                    self.assertTrue(harmonic_notes)
                    self.assertTrue(
                        all(note % 12 in expected for note in harmonic_notes),
                        harmonic_notes,
                    )

    def test_live_bass_inversion_does_not_transpose_the_generated_pattern(self) -> None:
        renderer, engine = self.create_renderer(
            "swing_foxtrot", tempo_bpm=60, sample_rate=100
        )
        a7_over_e = ChordState(
            9,
            ChordQuality.DOMINANT_SEVENTH,
            4,
            1.0,
            ("test",),
            0,
        )

        renderer.render(400, a7_over_e)

        bass_pitch_classes = {
            note % 12 for channel, note, _velocity in engine.note_ons if channel == 0
        }
        self.assertEqual(bass_pitch_classes, {1, 4, 7})

    def test_harmony_change_is_applied_at_the_next_audio_chunk(self) -> None:
        renderer, engine = self.create_renderer()
        renderer.render(20, chord())
        prior_note_count = len(engine.note_ons)

        renderer.render(20, chord(7, ChordQuality.MINOR))

        new_notes = engine.note_ons[prior_note_count:]
        self.assertTrue(new_notes)
        self.assertTrue(any(note % 12 == 7 for _channel, note, _velocity in new_notes))
        self.assertTrue(
            all((channel, 120, 0) in engine.controls for channel in range(4))
        )
        self.assertTrue(
            all((channel, 123, 0) in engine.controls for channel in range(4))
        )

    def test_rendered_position_is_reported_as_integer_ticks(self) -> None:
        renderer, _ = self.create_renderer(tempo_bpm=60, sample_rate=100)

        renderer.render(150, chord())

        self.assertEqual(renderer.position_ticks, TRANSPORT_TICKS_PER_BEAT * 3 // 2)

    def test_intro_and_ending_keep_the_existing_four_bar_contract(self) -> None:
        renderer, _ = self.create_renderer(tempo_bpm=60, sample_rate=100)
        renderer.start_intro()
        renderer.render(1_600, chord())
        self.assertEqual(renderer.section, DemoSection.MAIN)

        renderer.request_ending()
        renderer.render(400, chord())
        self.assertEqual(renderer.section, DemoSection.ENDING)
        renderer.render(1_600, chord())
        self.assertEqual(renderer.section, DemoSection.STOPPED)

    def test_close_releases_native_engine_once(self) -> None:
        renderer, engine = self.create_renderer()

        renderer.close()
        renderer.close()

        self.assertTrue(engine.closed)


if __name__ == "__main__":
    unittest.main()
