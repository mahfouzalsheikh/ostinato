from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

from ostinato.styles.models import (
    ChordVariation,
    ControlChangeEvent,
    NoteEvent,
    PitchBendEvent,
    ProgramChangeEvent,
    Style,
    StyleElement,
    StyleElementType,
    StyleSource,
    StyleTrack,
    StyleTrackRole,
)
from ostinato.styles.offline_audio import render_style_variation_to_wav


class FakeOfflineSynth:
    def __init__(self) -> None:
        self.frame = 0
        self.programs: list[tuple[int, int, int, int]] = []
        self.controls: list[tuple[int, int, int, int]] = []
        self.pitch_bends: list[tuple[int, int, int]] = []
        self.note_ons: list[tuple[int, int, int, int]] = []
        self.note_offs: list[tuple[int, int, int]] = []
        self.gains: list[float] = []
        self.closed = False

    def program_select(self, channel: int, bank: int, program: int) -> None:
        self.programs.append((self.frame, channel, bank, program))

    def control_change(self, channel: int, controller: int, value: int) -> None:
        self.controls.append((self.frame, channel, controller, value))

    def pitch_bend(self, channel: int, value: int) -> None:
        self.pitch_bends.append((self.frame, channel, value))

    def set_gain(self, gain: float) -> None:
        self.gains.append(gain)

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self.note_ons.append((self.frame, channel, note, velocity))

    def note_off(self, channel: int, note: int) -> None:
        self.note_offs.append((self.frame, channel, note))

    def render(self, frame_count: int) -> bytes:
        self.frame += frame_count
        return bytes(frame_count * 4)

    def close(self) -> None:
        self.closed = True


class ImportedStyleAudioTests(unittest.TestCase):
    def test_renders_integer_tick_timeline_with_explicit_gm_fallback(self) -> None:
        synth = FakeOfflineSynth()
        style = _style()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "variation.wav"
            report = render_style_variation_to_wav(
                style,
                output,
                Path("/configured/test.sf2"),
                sample_rate=1_000,
                tail_seconds=0,
                engine_factory=lambda _config, _path: synth,
            )
            with wave.open(str(output), "rb") as rendered:
                self.assertEqual(rendered.getframerate(), 1_000)
                self.assertEqual(rendered.getnframes(), 500)

        self.assertEqual(report.frame_count, 500)
        self.assertEqual(report.note_count, 2)
        self.assertEqual(report.source_pitch_transposition, "none")
        self.assertIn((0, 8, 0, 33), synth.programs)
        self.assertIn((0, 9, 128, 0), synth.programs)
        self.assertIn((125, 8, 8320), synth.pitch_bends)
        self.assertIn((500, 8, 36), synth.note_offs)
        self.assertTrue(synth.closed)

    def test_rejects_a_missing_section_without_starting_the_synth(self) -> None:
        with self.assertRaisesRegex(ValueError, "no fill_1 Chord Variation 1"):
            render_style_variation_to_wav(
                _style(),
                Path("unused.wav"),
                Path("/configured/test.sf2"),
                element_type=StyleElementType.FILL_1,
                engine_factory=lambda _config, _path: FakeOfflineSynth(),
            )


def _style() -> Style:
    bass = StyleTrack(
        role=StyleTrackRole.BASS,
        source_name="Bass",
        midi_channel=8,
        program=33,
        bank_msb=121,
        bank_lsb=3,
        events=(
            ControlChangeEvent(0, 11, 96, 8),
            ControlChangeEvent(0, 0, 121, 8),
            ControlChangeEvent(0, 32, 3, 8),
            ProgramChangeEvent(0, 33, 8),
            NoteEvent(0, 384, 36, 90, 8),
            PitchBendEvent(96, 128, 8),
        ),
    )
    drums = StyleTrack(
        role=StyleTrackRole.DRUM,
        source_name="Drum",
        midi_channel=9,
        program=4,
        bank_msb=120,
        bank_lsb=0,
        events=(NoteEvent(0, 96, 36, 100, 9),),
    )
    return Style(
        version=1,
        id="korg-test",
        name="KORG test",
        source=StyleSource("KORG", "test", "test.STY"),
        ticks_per_beat=384,
        tempo_microseconds_per_beat=500_000,
        time_signature=(4, 4),
        elements=(
            StyleElement(
                type=StyleElementType.VARIATION_1,
                name="Variation 1",
                chord_variations=(
                    ChordVariation(
                        number=1,
                        source_chord=None,
                        length_ticks=384,
                        tracks=(bass, drums),
                    ),
                ),
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
