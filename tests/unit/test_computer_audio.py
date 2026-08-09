from __future__ import annotations

import io
import unittest

from ostinato.computer_audio import (
    DemoArrangementRenderer,
    DemoAudioConfig,
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

    def test_root_and_quality_change_the_rendered_harmony(self) -> None:
        config = DemoAudioConfig()
        c_major = DemoArrangementRenderer(config).render(24_000, chord(0))
        g_minor = DemoArrangementRenderer(config).render(
            24_000, chord(7, ChordQuality.MINOR)
        )

        self.assertNotEqual(c_major, g_minor)

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


if __name__ == "__main__":
    unittest.main()
