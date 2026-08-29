from __future__ import annotations

import io
import math
import unittest
from array import array
from unittest.mock import patch

from ostinato.computer_audio import (
    DEMO_STYLES,
    TRANSPORT_TICKS_PER_BEAT,
    AlpinePolkaRenderer,
    BossaNovaRenderer,
    ClassicTangoRenderer,
    ClassicWaltzRenderer,
    DemoArrangementRenderer,
    DemoAudioConfig,
    DemoSection,
    SwingFoxtrotRenderer,
    run_audible_keyboard,
)
from ostinato.domain import ChordQuality, ChordState


def chord(root: int, quality: ChordQuality = ChordQuality.MAJOR) -> ChordState:
    return ChordState(
        root_pitch_class=root,
        quality=quality,
        bass_pitch_class=None,
        confidence=1.0,
        source_event_ids=("test",),
        recognized_at_ns=0,
    )


class DemoAudioConfigTests(unittest.TestCase):
    def test_rejects_tempos_outside_the_documented_demo_range(self) -> None:
        for tempo in (39, 241):
            with self.subTest(tempo=tempo), self.assertRaises(ValueError):
                DemoAudioConfig(tempo_bpm=tempo)

    def test_scripted_keys_are_rejected_without_opening_audio(self) -> None:
        output = io.StringIO()

        exit_code = run_audible_keyboard(
            keys="zaq", json_output=False, tempo_bpm=120, output_stream=output
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("cannot be combined", output.getvalue())


class DemoArrangementRendererTests(unittest.TestCase):
    def test_demo_identifies_its_original_style(self) -> None:
        self.assertEqual(DemoArrangementRenderer.STYLE_NAME, "modern_tango")
        self.assertEqual(DemoArrangementRenderer.OUTPUT_MODE, "procedural_pcm")

    def test_catalog_contains_six_distinct_original_styles(self) -> None:
        self.assertEqual(
            set(DEMO_STYLES),
            {
                "modern_tango",
                "classic_tango",
                "classic_waltz",
                "bossa_nova",
                "swing_foxtrot",
                "alpine_polka",
            },
        )
        self.assertEqual(DEMO_STYLES["modern_tango"].beats_per_bar, 4)
        self.assertEqual(DEMO_STYLES["classic_tango"].beats_per_bar, 4)
        self.assertEqual(DEMO_STYLES["classic_waltz"].beats_per_bar, 3)
        self.assertEqual(DEMO_STYLES["alpine_polka"].beats_per_bar, 2)
        self.assertTrue(all(style.description for style in DEMO_STYLES.values()))

        config = DemoAudioConfig()
        rendered = {
            definition.renderer(config).render(8_000, chord(0))
            for definition in DEMO_STYLES.values()
        }

        self.assertEqual(len(rendered), len(DEMO_STYLES))

    def test_every_style_has_a_valid_four_bar_phrase(self) -> None:
        for definition in DEMO_STYLES.values():
            renderer = definition.renderer
            with self.subTest(style=definition.id):
                self.assertEqual(len(renderer._GROOVE), 4)
                self.assertEqual(len(renderer._PHRASE_DYNAMICS), 4)
                for groove in renderer._GROOVE:
                    self.assertEqual(
                        len(groove.bass_onsets), len(groove.bass_intervals)
                    )
                    for onsets in (
                        groove.bass_onsets,
                        groove.chord_onsets,
                        groove.kick_onsets,
                        groove.snare_onsets,
                        groove.auxiliary_onsets,
                    ):
                        self.assertTrue(
                            all(
                                0.0 <= onset < renderer.BEATS_PER_BAR
                                for onset in onsets
                            )
                        )

    def test_each_style_intro_and_ending_span_four_bars(self) -> None:
        renderers = (
            DemoArrangementRenderer,
            ClassicTangoRenderer,
            ClassicWaltzRenderer,
            BossaNovaRenderer,
            SwingFoxtrotRenderer,
            AlpinePolkaRenderer,
        )
        for renderer_type in renderers:
            with self.subTest(style=renderer_type.STYLE_NAME):
                renderer = renderer_type(DemoAudioConfig(tempo_bpm=60, sample_rate=100))
                section_frames = round(renderer_type.BEATS_PER_BAR * 4 * 100)
                renderer.start_intro()
                renderer.render(section_frames, chord(0))
                self.assertEqual(renderer.section, DemoSection.MAIN)

                renderer.request_ending()
                renderer.render(round(renderer_type.BEATS_PER_BAR * 100), chord(0))
                self.assertEqual(renderer.section, DemoSection.ENDING)
                renderer.render(section_frames, chord(0))
                self.assertEqual(renderer.section, DemoSection.STOPPED)

    def test_waltz_intro_and_ending_each_span_four_three_beat_bars(self) -> None:
        renderer = ClassicWaltzRenderer(DemoAudioConfig(tempo_bpm=60, sample_rate=100))
        renderer.start_intro()
        renderer.render(1_200, chord(0))
        self.assertEqual(renderer.section, DemoSection.MAIN)

        renderer.request_ending()
        renderer.render(300, chord(0))
        self.assertEqual(renderer.section, DemoSection.ENDING)
        renderer.render(1_200, chord(0))
        self.assertEqual(renderer.section, DemoSection.STOPPED)

    def test_mastered_pcm_is_loud_without_reaching_integer_full_scale(self) -> None:
        renderer = DemoArrangementRenderer(DemoAudioConfig())

        pcm = array("h", renderer.render(48_000, chord(9, ChordQuality.MINOR)))
        mono = pcm[::2]
        peak = max(abs(sample) for sample in mono)
        rms = math.sqrt(sum(sample * sample for sample in mono) / len(mono))

        self.assertGreater(peak, 20_000)
        self.assertLessEqual(peak, DemoArrangementRenderer.OUTPUT_LIMIT)
        self.assertGreater(rms, 4_000)

    def test_drum_noise_is_deterministic_without_short_window_repetition(self) -> None:
        first = [DemoArrangementRenderer._noise(frame) for frame in range(32)]
        second = [DemoArrangementRenderer._noise(frame) for frame in range(32)]

        self.assertEqual(first, second)
        self.assertEqual(len(set(first)), len(first))
        self.assertTrue(all(-1.0 <= value <= 1.0 for value in first))

    def test_no_chord_renders_stereo_silence_and_advances_exactly(self) -> None:
        renderer = DemoArrangementRenderer(DemoAudioConfig())

        pcm = renderer.render(100, None)

        self.assertEqual(pcm, bytes(100 * 2 * 2))
        self.assertEqual(renderer.frame_position, 100)

    def test_chord_renders_audible_deterministic_pcm(self) -> None:
        config = DemoAudioConfig()
        first = DemoArrangementRenderer(config)
        second = DemoArrangementRenderer(config)

        first_pcm = first.render(24_000, chord(0))
        second_pcm = second.render(24_000, chord(0))

        self.assertEqual(first_pcm, second_pcm)
        self.assertNotEqual(first_pcm, bytes(len(first_pcm)))

    def test_instrument_panning_produces_a_real_stereo_field(self) -> None:
        pcm = array(
            "h", DemoArrangementRenderer(DemoAudioConfig()).render(8_000, chord(0))
        )

        self.assertNotEqual(pcm[::2], pcm[1::2])

    def test_root_and_quality_change_the_rendered_harmony(self) -> None:
        config = DemoAudioConfig()
        c_major = DemoArrangementRenderer(config).render(24_000, chord(0))
        g_minor = DemoArrangementRenderer(config).render(
            24_000, chord(7, ChordQuality.MINOR)
        )

        self.assertNotEqual(c_major, g_minor)

    def test_procedural_string_register_preserves_the_chord_pitch_classes(
        self,
    ) -> None:
        renderer = DemoArrangementRenderer(DemoAudioConfig())
        observed_notes: list[int] = []

        def frequency(note: int) -> float:
            observed_notes.append(note)
            return 440.0

        with patch.object(renderer, "_midi_frequency", side_effect=frequency):
            renderer._render_strings(
                frame=0,
                chord=chord(8),
                bar_phase=0.0,
                final_ending_bar=False,
            )

        self.assertEqual({note % 12 for note in observed_notes}, {0, 3, 8})

    def test_reset_returns_the_transport_to_the_same_bar_start(self) -> None:
        renderer = DemoArrangementRenderer(DemoAudioConfig())
        expected = renderer.render(4_000, chord(0))
        renderer.render(1_000, chord(7))

        renderer.reset()

        self.assertEqual(renderer.render(4_000, chord(0)), expected)

    def test_tempo_change_preserves_position_and_changes_subsequent_speed(self) -> None:
        renderer = DemoArrangementRenderer(DemoAudioConfig(tempo_bpm=120))
        renderer.render(24_000, chord(0))
        self.assertAlmostEqual(renderer.beat_position, 1.0)

        renderer.set_tempo(60)
        renderer.render(24_000, chord(0))

        self.assertEqual(renderer.tempo_bpm, 60)
        self.assertAlmostEqual(renderer.beat_position, 1.5)
        self.assertEqual(renderer.position_ticks, TRANSPORT_TICKS_PER_BEAT * 3 // 2)

    def test_main_pattern_uses_three_three_two_in_every_bar(self) -> None:
        self.assertEqual(DemoArrangementRenderer.BEATS_PER_BAR, 4.0)
        self.assertEqual(DemoArrangementRenderer.SYNCOPATION_GROUPS, (1.5, 1.5, 1.0))
        self.assertEqual(sum(DemoArrangementRenderer.SYNCOPATION_GROUPS), 4.0)
        self.assertEqual(DemoArrangementRenderer._BASS_ONSETS, (0.0, 1.5, 3.0))
        self.assertEqual(DemoArrangementRenderer._CHORD_ONSETS, (0.5, 2.0, 3.5))

    def test_classic_tango_uses_marcato_and_sincopa_without_drum_kit(self) -> None:
        first, second, third, _ = ClassicTangoRenderer._GROOVE

        self.assertEqual(first.bass_onsets, (0.0, 1.0, 2.0, 3.0))
        self.assertEqual(second.bass_onsets, (0.0, 2.0))
        self.assertEqual(third.bass_onsets, (0.0, 1.5, 2.0, 3.5))
        self.assertTrue(
            all(groove.hat_onsets == () for groove in ClassicTangoRenderer._GROOVE)
        )
        self.assertEqual(ClassicTangoRenderer._MAIN_LEVELS.drums, 0.0)

    def test_bossa_separates_steady_bass_from_two_bar_syncopated_comping(self) -> None:
        first, second, *_ = BossaNovaRenderer._GROOVE

        self.assertEqual(first.bass_onsets, (0.0, 2.0))
        self.assertEqual(first.bass_roles, ("root", "fifth"))
        self.assertNotEqual(first.chord_onsets, second.chord_onsets)
        self.assertEqual(first.reed_onsets, ())
        self.assertEqual(first.pad_onsets, ())

    def test_swing_walk_uses_quality_aware_safe_chord_tones(self) -> None:
        first = SwingFoxtrotRenderer._GROOVE[0]

        self.assertEqual(first.bass_onsets, (0.0, 1.0, 2.0, 3.0))
        self.assertEqual(first.bass_roles, ("root", "third", "fifth", "color"))
        self.assertEqual(
            SwingFoxtrotRenderer._bass_role_interval(ChordQuality.MINOR, "third"),
            3,
        )
        self.assertEqual(
            SwingFoxtrotRenderer._bass_role_interval(ChordQuality.MINOR, "color"),
            12,
        )
        self.assertEqual(
            SwingFoxtrotRenderer._bass_role_interval(
                ChordQuality.DOMINANT_SEVENTH, "color"
            ),
            10,
        )

    def test_polka_preserves_bass_then_upbeat_chord_oom_pah(self) -> None:
        for groove in AlpinePolkaRenderer._GROOVE[:3]:
            self.assertEqual(groove.bass_onsets, (0.0, 1.0))
            self.assertEqual(groove.chord_onsets, (0.5, 1.5))

    def test_four_measure_intro_transitions_to_main(self) -> None:
        renderer = DemoArrangementRenderer(
            DemoAudioConfig(tempo_bpm=120, sample_rate=100)
        )
        renderer.start_intro()
        self.assertEqual(renderer.section, DemoSection.INTRO)

        renderer.render(800, chord(9, ChordQuality.MINOR))

        self.assertEqual(renderer.section, DemoSection.MAIN)

    def test_ending_starts_next_bar_then_stops_after_four_measures(self) -> None:
        renderer = DemoArrangementRenderer(
            DemoAudioConfig(tempo_bpm=120, sample_rate=100)
        )
        renderer.request_ending()
        self.assertEqual(renderer.section, DemoSection.MAIN)

        renderer.render(200, chord(9, ChordQuality.MINOR))
        self.assertEqual(renderer.section, DemoSection.ENDING)
        ending_pcm = renderer.render(800, chord(9, ChordQuality.MINOR))
        self.assertNotEqual(ending_pcm, bytes(len(ending_pcm)))
        self.assertEqual(renderer.section, DemoSection.STOPPED)

        silence = renderer.render(20, chord(9, ChordQuality.MINOR))
        self.assertEqual(silence, bytes(len(silence)))

        renderer.resume_if_stopped()
        self.assertEqual(renderer.section, DemoSection.MAIN)

    def test_intro_and_ending_orchestrate_six_independent_parts(self) -> None:
        intro_first = DemoArrangementRenderer._ensemble_levels(DemoSection.INTRO, 0.0)
        intro_last = DemoArrangementRenderer._ensemble_levels(DemoSection.INTRO, 12.0)
        ending_first = DemoArrangementRenderer._ensemble_levels(DemoSection.ENDING, 0.0)
        ending_last = DemoArrangementRenderer._ensemble_levels(DemoSection.ENDING, 12.0)

        self.assertEqual(intro_first.bass, 0.0)
        self.assertEqual(intro_first.piano, 0.0)
        self.assertEqual(intro_first.drums, 0.0)
        self.assertGreater(intro_first.bandoneon, 0.0)
        self.assertGreater(intro_first.percussion, 0.0)
        self.assertGreater(intro_first.strings, 0.0)
        instrument_names = (
            "bass",
            "piano",
            "bandoneon",
            "drums",
            "percussion",
            "strings",
        )
        self.assertTrue(
            all(getattr(intro_last, name) > 0.0 for name in instrument_names)
        )
        self.assertLess(ending_last.drums, ending_first.drums)
        self.assertLess(ending_last.percussion, ending_first.percussion)
        self.assertGreater(ending_last.strings, ending_first.strings)

    def test_pulse_lookup_wraps_to_the_previous_bar(self) -> None:
        onsets = (0.5, 2.0, 3.5)

        pulse, elapsed = DemoArrangementRenderer._pulse_at(0.25, onsets)

        self.assertEqual(pulse, 2)
        self.assertAlmostEqual(elapsed, 0.75)


if __name__ == "__main__":
    unittest.main()
