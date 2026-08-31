from __future__ import annotations

import ctypes
import tempfile
import unittest
from pathlib import Path

from ostinato.arranger import ProceduralArrangerAudio
from ostinato.computer_audio import DEMO_STYLES, DemoAudioConfig
from ostinato.domain import ChordQuality, ChordState
from ostinato.sfz_audio import (
    BASS_CHANNEL,
    CELLO_CHANNEL,
    FLUTE_CHANNEL,
    PIANO_CHANNEL,
    STYLE_SFZ_MASTER_GAINS,
    STYLE_SFZ_PROFILES,
    VIOLIN_CHANNEL,
    SfzError,
    SfzStyleArrangementRenderer,
    SfzStylePaths,
    SfzStyleRackEngine,
    SfzWaltzArrangementRenderer,
    SfzWaltzPaths,
    SfzWaltzRackEngine,
)
from ostinato.soundfont_audio import DRUM_CHANNEL


def make_paths(directory: Path) -> SfzWaltzPaths:
    values: dict[str, Path] = {}
    for field in ("library", "piano", "bass", "flute", "cello", "violin", "drums"):
        path = directory / f"{field}.sfz"
        path.write_bytes(b"test")
        values[field] = path
    return SfzWaltzPaths(**values)


def make_style_paths(directory: Path) -> SfzStylePaths:
    values: dict[str, Path] = {}
    for field in (
        "acoustic_guitar",
        "electric_guitar",
        "electric_bass_finger",
        "electric_bass_pick",
        "drum_kit",
        "clarinet",
        "trumpet",
    ):
        path = directory / f"{field}.sfz"
        path.write_bytes(b"test")
        values[field] = path
    return SfzStylePaths(waltz=make_paths(directory), **values)


class FakeVoice:
    def __init__(self, value: float = 0.02) -> None:
        self.value = value
        self.notes_on: list[tuple[int, int]] = []
        self.notes_off: list[int] = []
        self.controls: list[tuple[int, int]] = []
        self.sound_off_count = 0
        self.closed = False
        self.render_sizes: list[int] = []

    def note_on(self, note: int, velocity: int) -> None:
        self.notes_on.append((note, velocity))

    def note_off(self, note: int) -> None:
        self.notes_off.append(note)

    def control_change(self, controller: int, value: int) -> None:
        self.controls.append((controller, value))

    def all_sound_off(self) -> None:
        self.sound_off_count += 1

    def render(self, frame_count: int) -> tuple[ctypes.Array[ctypes.c_float], ...]:
        self.render_sizes.append(frame_count)
        channel = (ctypes.c_float * frame_count)(*[self.value] * frame_count)
        return channel, channel

    def close(self) -> None:
        self.closed = True


class RecordingEngine:
    def __init__(self) -> None:
        self.notes_on: list[tuple[int, int, int]] = []
        self.notes_off: list[tuple[int, int]] = []
        self.controls: list[tuple[int, int, int]] = []
        self.closed = False
        self.frame = 0
        self.note_frames: list[tuple[int, int]] = []

    def program_select(self, channel: int, bank: int, program: int) -> None:
        pass

    def control_change(self, channel: int, controller: int, value: int) -> None:
        self.controls.append((channel, controller, value))

    def set_gain(self, gain: float) -> None:
        pass

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self.notes_on.append((channel, note, velocity))
        self.note_frames.append((channel, self.frame))

    def note_off(self, channel: int, note: int) -> None:
        self.notes_off.append((channel, note))

    def render(self, frame_count: int) -> bytes:
        self.frame += frame_count
        return bytes(frame_count * 4)

    def close(self) -> None:
        self.closed = True


class SfzAudioTests(unittest.TestCase):
    def test_environment_requires_the_complete_explicit_rack(self) -> None:
        self.assertIsNone(SfzWaltzPaths.from_environment({}))

        with self.assertRaisesRegex(SfzError, "incomplete Classic Waltz SFZ rack"):
            SfzWaltzPaths.from_environment({"OSTINATO_SFIZZ_LIBRARY": "/sfizz"})

    def test_rack_routes_channels_mixes_pcm_and_closes_voices(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            paths = make_paths(Path(temporary_name))
            voices: dict[str, FakeVoice] = {}

            def factory(path: Path) -> FakeVoice:
                voice = FakeVoice()
                voices[path.stem] = voice
                return voice

            rack = SfzWaltzRackEngine(
                DemoAudioConfig(sample_rate=1_000, chunk_frames=10),
                paths,
                voice_factory=factory,
            )
            rack.note_on(BASS_CHANNEL, 36, 96)
            rack.note_off(BASS_CHANNEL, 36)
            pcm = rack.render(25)
            rack.close()

        self.assertEqual(voices["bass"].notes_on, [(36, 96)])
        self.assertEqual(voices["bass"].notes_off, [36])
        self.assertEqual(len(pcm), 100)
        self.assertNotEqual(pcm, bytes(100))
        self.assertTrue(
            all(voice.render_sizes == [10, 10, 5] for voice in voices.values())
        )
        self.assertTrue(all(voice.closed for voice in voices.values()))

    def test_waltz_renderer_uses_six_dedicated_instrument_channels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            paths = make_paths(Path(temporary_name))
            engine = RecordingEngine()
            config = DemoAudioConfig(
                tempo_bpm=96,
                sample_rate=1_000,
                chunk_frames=100,
            )
            renderer = SfzWaltzArrangementRenderer(
                config,
                paths,
                engine_factory=lambda _config, _paths: engine,
            )
            chord = ChordState(
                2,
                ChordQuality.MINOR,
                2,
                1.0,
                ("test",),
                0,
            )

            renderer.render(round(3 * 60 * config.sample_rate / 96), chord)
            renderer.close()

        channels = {channel for channel, _note, _velocity in engine.notes_on}
        self.assertEqual(
            channels,
            {
                BASS_CHANNEL,
                PIANO_CHANNEL,
                FLUTE_CHANNEL,
                CELLO_CHANNEL,
                VIOLIN_CHANNEL,
                DRUM_CHANNEL,
            },
        )
        self.assertTrue(engine.closed)

    def test_audio_service_reports_sfizz_only_for_the_built_in_waltz(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            audio = ProceduralArrangerAudio(
                soundfont_path="/sounds/hq.sf3",
                soundfont_name="HQ",
                sfz_waltz_paths=make_paths(Path(temporary_name)),
            )

            self.assertEqual(audio.synthesis_engine, "FluidSynth · HQ")
            audio.select_style("classic_waltz")

        self.assertEqual(audio.synthesis_engine, "sfizz · open sampled orchestra")

    def test_style_paths_reject_a_partial_genre_rack(self) -> None:
        with self.assertRaisesRegex(SfzError, "incomplete built-in style SFZ rack"):
            SfzStylePaths.from_environment(
                {"OSTINATO_STYLE_SFZ_ACOUSTIC_GUITAR": "/guitar.sfz"}
            )

    def test_every_non_waltz_builtin_has_an_explicit_genre_profile(self) -> None:
        self.assertEqual(set(STYLE_SFZ_PROFILES), set(DEMO_STYLES) - {"classic_waltz"})
        self.assertEqual(set(STYLE_SFZ_MASTER_GAINS), set(STYLE_SFZ_PROFILES))
        for style_id, profile in STYLE_SFZ_PROFILES.items():
            with self.subTest(style=style_id):
                self.assertTrue(profile.essential_roles)
                self.assertTrue(
                    set(profile.essential_roles).issubset(
                        {"bass", "comp", "fill", "pad", "drums"}
                    )
                )

    def test_tango_profiles_make_piano_an_essential_prominent_voice(self) -> None:
        for style_id in ("modern_tango", "classic_tango"):
            with self.subTest(style=style_id):
                profile = STYLE_SFZ_PROFILES[style_id]
                self.assertEqual(profile.comp, "piano")
                self.assertIn("comp", profile.essential_roles)
                self.assertGreater(profile.comp_gain, profile.bass_gain * 2)

    def test_recorded_drum_kits_have_style_specific_audibility_calibration(
        self,
    ) -> None:
        expected = {
            "modern_tango": 0.95,
            "classic_tango": 0.0,
            "bossa_nova": 5.0,
            "swing_foxtrot": 1.7,
            "alpine_polka": 0.75,
            "motown_soul": 1.9,
            "funk_pocket": 1.25,
            "soft_pop": 4.5,
            "country_two_step": 1.3,
            "reggae_one_drop": 4.5,
            "brazilian_samba": 2.8,
            "new_orleans_chacha": 5.0,
            "blues_shuffle": 1.1,
        }
        self.assertEqual(
            {
                style_id: profile.drums_gain
                for style_id, profile in STYLE_SFZ_PROFILES.items()
            },
            expected,
        )
        self.assertEqual(SfzWaltzRackEngine._INSTRUMENTS[DRUM_CHANNEL][1], 3.5)

    def test_genre_rack_loads_the_profile_instruments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            paths = make_style_paths(Path(temporary_name))
            loaded: list[Path] = []

            def factory(path: Path) -> FakeVoice:
                loaded.append(path)
                return FakeVoice()

            rack = SfzStyleRackEngine(
                DemoAudioConfig(sample_rate=1_000, chunk_frames=10),
                paths,
                STYLE_SFZ_PROFILES["bossa_nova"],
                voice_factory=factory,
            )
            rack.close()

        self.assertEqual(len(loaded), 5)
        self.assertIn(paths.acoustic_guitar, loaded)
        self.assertIn(paths.electric_bass_finger, loaded)
        self.assertIn(paths.drum_kit, loaded)

    def test_genre_renderer_uses_all_roles_and_staggers_sampled_chords(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            paths = make_style_paths(Path(temporary_name))
            engine = RecordingEngine()
            config = DemoAudioConfig(
                tempo_bpm=112,
                sample_rate=1_000,
                chunk_frames=10,
            )
            renderer = SfzStyleArrangementRenderer(
                "modern_tango",
                config,
                paths,
                engine_factory=lambda _config, _paths, _profile: engine,
            )
            chord = ChordState(0, ChordQuality.MAJOR, None, 1.0, ("genre-test",), 0)

            renderer.render(round(4 * 60 * config.sample_rate / 112), chord)
            renderer.close()

        channels = {channel for channel, _note, _velocity in engine.notes_on}
        self.assertEqual(channels, {0, 1, 2, 3, DRUM_CHANNEL})
        comp_frames = {
            frame for channel, frame in engine.note_frames if channel == PIANO_CHANNEL
        }
        self.assertGreater(len(comp_frames), 1)
        self.assertTrue(engine.notes_off)

    def test_audio_service_reports_open_samples_for_other_builtins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            audio = ProceduralArrangerAudio(
                soundfont_path="/sounds/hq.sf3",
                soundfont_name="HQ",
                sfz_style_paths=make_style_paths(Path(temporary_name)),
            )

            self.assertEqual(
                audio.synthesis_engine, "sfizz · open sampled genre ensemble"
            )
            audio.select_style("classic_waltz")

        self.assertEqual(audio.synthesis_engine, "sfizz · open sampled orchestra")


if __name__ == "__main__":
    unittest.main()
