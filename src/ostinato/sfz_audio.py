"""Genre-profiled open-sample SFZ racks for the built-in arrangements."""

from __future__ import annotations

import ctypes
import heapq
import os
from array import array
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Protocol, Self

from ostinato.computer_audio import (
    BASS_C_NOTE,
    LOW_C_NOTE,
    MIDDLE_C_NOTE,
    UPPER_C_NOTE,
    DemoAudioConfig,
    EnsembleLevels,
    GrooveBar,
)
from ostinato.domain import ChordState
from ostinato.soundfont_audio import (
    DRUM_CHANNEL,
    KICK_NOTE,
    SoundFontArrangementRenderer,
    SoundFontPalette,
    SynthEngine,
    _SynthEvent,
)

BASS_CHANNEL = 0
PIANO_CHANNEL = 1
FLUTE_CHANNEL = 2
CELLO_CHANNEL = 3
VIOLIN_CHANNEL = 4
WALTZ_MELODIC_CHANNELS = (
    BASS_CHANNEL,
    PIANO_CHANNEL,
    FLUTE_CHANNEL,
    CELLO_CHANNEL,
    VIOLIN_CHANNEL,
)

_ENVIRONMENT_PATHS = {
    "library": "OSTINATO_SFIZZ_LIBRARY",
    "piano": "OSTINATO_WALTZ_SFZ_PIANO",
    "bass": "OSTINATO_WALTZ_SFZ_BASS",
    "flute": "OSTINATO_WALTZ_SFZ_FLUTE",
    "cello": "OSTINATO_WALTZ_SFZ_CELLO",
    "violin": "OSTINATO_WALTZ_SFZ_VIOLIN",
    "drums": "OSTINATO_WALTZ_SFZ_DRUMS",
}

_STYLE_ENVIRONMENT_PATHS = {
    "acoustic_guitar": "OSTINATO_STYLE_SFZ_ACOUSTIC_GUITAR",
    "electric_guitar": "OSTINATO_STYLE_SFZ_ELECTRIC_GUITAR",
    "electric_bass_finger": "OSTINATO_STYLE_SFZ_ELECTRIC_BASS_FINGER",
    "electric_bass_pick": "OSTINATO_STYLE_SFZ_ELECTRIC_BASS_PICK",
    "drum_kit": "OSTINATO_STYLE_SFZ_DRUM_KIT",
    "clarinet": "OSTINATO_STYLE_SFZ_CLARINET",
    "trumpet": "OSTINATO_STYLE_SFZ_TRUMPET",
}


class SfzError(RuntimeError):
    """A configured SFZ engine or open sample instrument failed."""


@dataclass(frozen=True, slots=True)
class SfzWaltzPaths:
    """Exact configured paths for the sampler and each recorded instrument."""

    library: Path
    piano: Path
    bass: Path
    flute: Path
    cello: Path
    violin: Path
    drums: Path

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> Self | None:
        values = environment if environment is not None else os.environ
        configured = {
            field: values.get(variable)
            for field, variable in _ENVIRONMENT_PATHS.items()
        }
        if not any(configured.values()):
            return None
        missing = [
            variable
            for field, variable in _ENVIRONMENT_PATHS.items()
            if not configured[field]
        ]
        if missing:
            raise SfzError(
                "incomplete Classic Waltz SFZ rack; missing " + ", ".join(missing)
            )
        return cls(**{field: Path(str(value)) for field, value in configured.items()})

    def validate(self) -> None:
        for field, variable in _ENVIRONMENT_PATHS.items():
            path = getattr(self, field)
            if not path.is_file():
                raise SfzError(f"{variable} does not identify a file: {path}")


@dataclass(frozen=True, slots=True)
class SfzStylePaths:
    """The accepted Waltz instruments plus open genre-rack additions."""

    waltz: SfzWaltzPaths
    acoustic_guitar: Path
    electric_guitar: Path
    electric_bass_finger: Path
    electric_bass_pick: Path
    drum_kit: Path
    clarinet: Path
    trumpet: Path

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> Self | None:
        values = environment if environment is not None else os.environ
        configured = {
            field: values.get(variable)
            for field, variable in _STYLE_ENVIRONMENT_PATHS.items()
        }
        if not any(configured.values()):
            return None
        missing = [
            variable
            for field, variable in _STYLE_ENVIRONMENT_PATHS.items()
            if not configured[field]
        ]
        if missing:
            raise SfzError(
                "incomplete built-in style SFZ rack; missing " + ", ".join(missing)
            )
        waltz = SfzWaltzPaths.from_environment(values)
        if waltz is None:
            raise SfzError(
                "the built-in style SFZ rack also requires the Classic Waltz rack"
            )
        return cls(
            waltz=waltz,
            **{field: Path(str(value)) for field, value in configured.items()},
        )

    def validate(self) -> None:
        self.waltz.validate()
        for field, variable in _STYLE_ENVIRONMENT_PATHS.items():
            path = getattr(self, field)
            if not path.is_file():
                raise SfzError(f"{variable} does not identify a file: {path}")

    def instrument(self, name: str) -> Path:
        waltz_paths = {
            "piano": self.waltz.piano,
            "upright_bass": self.waltz.bass,
            "flute": self.waltz.flute,
            "cello": self.waltz.cello,
            "violin": self.waltz.violin,
            "brushed_drums": self.waltz.drums,
        }
        if name in waltz_paths:
            return waltz_paths[name]
        style_paths = {
            "acoustic_guitar": self.acoustic_guitar,
            "electric_guitar": self.electric_guitar,
            "electric_bass_finger": self.electric_bass_finger,
            "electric_bass_pick": self.electric_bass_pick,
            "drum_kit": self.drum_kit,
            "clarinet": self.clarinet,
            "trumpet": self.trumpet,
        }
        try:
            return style_paths[name]
        except KeyError as error:
            raise SfzError(f"unknown open-sample instrument: {name}") from error


class _Voice(Protocol):
    def note_on(self, note: int, velocity: int) -> None: ...

    def note_off(self, note: int) -> None: ...

    def control_change(self, controller: int, value: int) -> None: ...

    def all_sound_off(self) -> None: ...

    def render(self, frame_count: int) -> tuple[ctypes.Array[ctypes.c_float], ...]: ...

    def close(self) -> None: ...


class _SfizzVoice:
    """One native sfizz synth loaded with one SFZ instrument."""

    def __init__(
        self,
        library: ctypes.CDLL,
        config: DemoAudioConfig,
        instrument_path: Path,
    ) -> None:
        self._library = library
        synth = library.sfizz_create_synth()
        if not synth:
            raise SfzError("sfizz could not allocate a synth")
        self._synth: int | None = synth
        library.sfizz_set_sample_rate(synth, float(config.sample_rate))
        library.sfizz_set_samples_per_block(synth, config.chunk_frames)
        if not library.sfizz_load_file(synth, os.fsencode(instrument_path)):
            self.close()
            raise SfzError(f"sfizz could not load instrument: {instrument_path}")

    def note_on(self, note: int, velocity: int) -> None:
        self._library.sfizz_send_note_on(self._require_synth(), 0, note, velocity)

    def note_off(self, note: int) -> None:
        self._library.sfizz_send_note_off(self._require_synth(), 0, note, 0)

    def control_change(self, controller: int, value: int) -> None:
        self._library.sfizz_send_cc(self._require_synth(), 0, controller, value)

    def all_sound_off(self) -> None:
        self._library.sfizz_all_sound_off(self._require_synth())

    def render(self, frame_count: int) -> tuple[ctypes.Array[ctypes.c_float], ...]:
        left = (ctypes.c_float * frame_count)()
        right = (ctypes.c_float * frame_count)()
        channels = (ctypes.POINTER(ctypes.c_float) * 2)(
            ctypes.cast(left, ctypes.POINTER(ctypes.c_float)),
            ctypes.cast(right, ctypes.POINTER(ctypes.c_float)),
        )
        self._library.sfizz_render_block(
            self._require_synth(), channels, 2, frame_count
        )
        return left, right

    def close(self) -> None:
        synth = self._synth
        if synth is not None:
            self._library.sfizz_free(synth)
            self._synth = None

    def _require_synth(self) -> int:
        if self._synth is None:
            raise SfzError("sfizz synth is closed")
        return self._synth


@dataclass(slots=True)
class _MixState:
    gain: float
    pan: float
    volume: float = 1.0


class _SfzRackEngine:
    """Mix independent sampled instruments into interleaved signed 16-bit PCM."""

    def __init__(
        self,
        config: DemoAudioConfig,
        library_path: Path,
        instruments: Mapping[int, tuple[Path, float, float]],
        *,
        voice_factory: Callable[[Path], _Voice] | None = None,
    ) -> None:
        if not library_path.is_file():
            raise SfzError(f"sfizz library does not identify a file: {library_path}")
        for path, _gain, _pan in instruments.values():
            if not path.is_file():
                raise SfzError(f"SFZ instrument does not identify a file: {path}")
        if voice_factory is None:
            library = ctypes.CDLL(str(library_path))
            self._bind_library(library)

            def create_voice(path: Path) -> _Voice:
                return _SfizzVoice(library, config, path)

            voice_factory = create_voice
        self._voices: dict[int, _Voice] = {}
        self._mix: dict[int, _MixState] = {}
        self._master_gain = 1.0
        self._block_frames = config.chunk_frames
        try:
            for channel, (path, gain, pan) in instruments.items():
                self._voices[channel] = voice_factory(path)
                self._mix[channel] = _MixState(gain, pan)
        except Exception:
            self.close()
            raise

    def program_select(self, channel: int, bank: int, program: int) -> None:
        """SFZ files are explicit instruments, so General MIDI programs are unused."""

    def control_change(self, channel: int, controller: int, value: int) -> None:
        voice = self._voice(channel)
        if controller == 7:
            self._mix[channel].volume = value / 127
        elif controller == 10:
            self._mix[channel].pan = value / 127
        elif controller in (120, 123):
            voice.all_sound_off()
        else:
            voice.control_change(controller, value)

    def set_gain(self, gain: float) -> None:
        self._master_gain = gain

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self._voice(channel).note_on(note, velocity)

    def note_off(self, channel: int, note: int) -> None:
        self._voice(channel).note_off(note)

    def render(self, frame_count: int) -> bytes:
        if frame_count < 0:
            raise ValueError("frame_count cannot be negative")
        if frame_count == 0:
            return b""
        samples = array("h")
        remaining = frame_count
        while remaining:
            block_frames = min(remaining, self._block_frames)
            rendered = {
                channel: voice.render(block_frames)
                for channel, voice in self._voices.items()
            }
            for frame in range(block_frames):
                left_mix = 0.0
                right_mix = 0.0
                for channel, (left, right) in rendered.items():
                    mix = self._mix[channel]
                    gain = self._master_gain * mix.gain * mix.volume
                    left_pan = min(1.0, 2.0 * (1.0 - mix.pan))
                    right_pan = min(1.0, 2.0 * mix.pan)
                    left_mix += left[frame] * gain * left_pan
                    right_mix += right[frame] * gain * right_pan
                samples.append(round(max(-1.0, min(0.999969, left_mix)) * 32767))
                samples.append(round(max(-1.0, min(0.999969, right_mix)) * 32767))
            remaining -= block_frames
        return samples.tobytes()

    def close(self) -> None:
        for voice in getattr(self, "_voices", {}).values():
            voice.close()
        if hasattr(self, "_voices"):
            self._voices.clear()

    def _voice(self, channel: int) -> _Voice:
        try:
            return self._voices[channel]
        except KeyError as error:
            raise SfzError(
                f"SFZ rack has no instrument on channel {channel}"
            ) from error

    @staticmethod
    def _bind_library(library: ctypes.CDLL) -> None:
        library.sfizz_create_synth.restype = ctypes.c_void_p
        library.sfizz_free.argtypes = [ctypes.c_void_p]
        library.sfizz_load_file.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        library.sfizz_load_file.restype = ctypes.c_bool
        library.sfizz_set_sample_rate.argtypes = [ctypes.c_void_p, ctypes.c_float]
        library.sfizz_set_samples_per_block.argtypes = [ctypes.c_void_p, ctypes.c_int]
        library.sfizz_send_note_on.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        library.sfizz_send_note_off.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        library.sfizz_send_cc.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        library.sfizz_all_sound_off.argtypes = [ctypes.c_void_p]
        library.sfizz_render_block.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_float)),
            ctypes.c_int,
            ctypes.c_int,
        ]


class SfzWaltzRackEngine(_SfzRackEngine):
    """The six-instrument rack accepted in the Classic Waltz listening test."""

    _INSTRUMENTS: ClassVar[dict[int, tuple[str, float, float]]] = {
        BASS_CHANNEL: ("bass", 0.78, 0.40),
        PIANO_CHANNEL: ("piano", 0.50, 0.47),
        FLUTE_CHANNEL: ("flute", 0.32, 0.68),
        CELLO_CHANNEL: ("cello", 0.30, 0.32),
        VIOLIN_CHANNEL: ("violin", 0.24, 0.72),
        # Swirly's brush samples are substantially quieter than its melodic
        # peers. This is sample normalization, before musical MIDI dynamics.
        DRUM_CHANNEL: ("drums", 3.50, 0.53),
    }

    def __init__(
        self,
        config: DemoAudioConfig,
        paths: SfzWaltzPaths,
        *,
        voice_factory: Callable[[Path], _Voice] | None = None,
    ) -> None:
        paths.validate()
        super().__init__(
            config,
            paths.library,
            {
                channel: (getattr(paths, field), gain, pan)
                for channel, (field, gain, pan) in self._INSTRUMENTS.items()
            },
            voice_factory=voice_factory,
        )


@dataclass(frozen=True, slots=True)
class StyleSfzProfile:
    """Recorded instrument choices for one built-in genre arrangement."""

    bass: str
    comp: str
    fill: str
    pad: str
    drums: str
    essential_roles: tuple[str, ...] = ("bass", "comp", "drums")
    bass_gain: float = 0.70
    comp_gain: float = 0.44
    fill_gain: float = 0.27
    pad_gain: float = 0.24
    drums_gain: float = 0.42


STYLE_SFZ_PROFILES: dict[str, StyleSfzProfile] = {
    "modern_tango": StyleSfzProfile(
        "upright_bass",
        "piano",
        "violin",
        "cello",
        "drum_kit",
        essential_roles=("bass", "comp", "fill"),
        bass_gain=0.38,
        comp_gain=0.92,
        fill_gain=0.36,
        pad_gain=0.32,
        drums_gain=0.95,
    ),
    "classic_tango": StyleSfzProfile(
        "upright_bass",
        "piano",
        "violin",
        "cello",
        "drum_kit",
        essential_roles=("bass", "comp", "fill", "pad"),
        bass_gain=0.38,
        comp_gain=0.92,
        fill_gain=0.40,
        pad_gain=0.38,
        drums_gain=0.0,
    ),
    "bossa_nova": StyleSfzProfile(
        "electric_bass_finger",
        "acoustic_guitar",
        "flute",
        "cello",
        "drum_kit",
        drums_gain=5.00,
    ),
    "swing_foxtrot": StyleSfzProfile(
        "upright_bass",
        "piano",
        "trumpet",
        "cello",
        "brushed_drums",
        essential_roles=("bass", "comp", "fill", "drums"),
        fill_gain=0.36,
        drums_gain=1.70,
    ),
    "alpine_polka": StyleSfzProfile(
        "upright_bass",
        "piano",
        "clarinet",
        "violin",
        "drum_kit",
        essential_roles=("bass", "comp", "fill", "drums"),
        fill_gain=0.34,
        drums_gain=0.75,
    ),
    "motown_soul": StyleSfzProfile(
        "electric_bass_finger",
        "piano",
        "trumpet",
        "cello",
        "drum_kit",
        essential_roles=("bass", "comp", "fill", "drums"),
        fill_gain=0.30,
        drums_gain=1.90,
    ),
    "funk_pocket": StyleSfzProfile(
        "electric_bass_finger",
        "electric_guitar",
        "trumpet",
        "cello",
        "drum_kit",
        essential_roles=("bass", "comp", "fill", "drums"),
        fill_gain=0.30,
        drums_gain=1.25,
    ),
    "soft_pop": StyleSfzProfile(
        "electric_bass_finger",
        "acoustic_guitar",
        "flute",
        "cello",
        "drum_kit",
        drums_gain=4.50,
    ),
    "country_two_step": StyleSfzProfile(
        "electric_bass_pick",
        "acoustic_guitar",
        "violin",
        "cello",
        "drum_kit",
        essential_roles=("bass", "comp", "fill", "drums"),
        drums_gain=1.30,
    ),
    "reggae_one_drop": StyleSfzProfile(
        "electric_bass_finger",
        "electric_guitar",
        "flute",
        "cello",
        "drum_kit",
        drums_gain=4.50,
    ),
    "brazilian_samba": StyleSfzProfile(
        "electric_bass_finger",
        "acoustic_guitar",
        "flute",
        "cello",
        "drum_kit",
        drums_gain=2.80,
    ),
    "new_orleans_chacha": StyleSfzProfile(
        "electric_bass_finger",
        "piano",
        "trumpet",
        "cello",
        "drum_kit",
        essential_roles=("bass", "comp", "fill", "drums"),
        comp_gain=0.56,
        fill_gain=0.34,
        drums_gain=5.00,
    ),
    "blues_shuffle": StyleSfzProfile(
        "electric_bass_pick",
        "piano",
        "flute",
        "cello",
        "drum_kit",
        drums_gain=1.10,
    ),
}

# Calibrated against the same four-bar GM reference at each style's default
# tempo. These are output trims only; they do not alter velocity-layer choice.
STYLE_SFZ_MASTER_GAINS: dict[str, float] = {
    "modern_tango": 6.25,
    "classic_tango": 5.00,
    "bossa_nova": 2.92,
    "swing_foxtrot": 4.04,
    "alpine_polka": 5.06,
    "motown_soul": 3.56,
    "funk_pocket": 4.69,
    "soft_pop": 2.29,
    "country_two_step": 7.34,
    "reggae_one_drop": 2.63,
    "brazilian_samba": 3.29,
    "new_orleans_chacha": 3.03,
    "blues_shuffle": 5.59,
}


class SfzStyleRackEngine(_SfzRackEngine):
    """Five-role rack whose recorded instruments are chosen by genre."""

    def __init__(
        self,
        config: DemoAudioConfig,
        paths: SfzStylePaths,
        profile: StyleSfzProfile,
        *,
        voice_factory: Callable[[Path], _Voice] | None = None,
    ) -> None:
        paths.validate()
        super().__init__(
            config,
            paths.waltz.library,
            {
                BASS_CHANNEL: (paths.instrument(profile.bass), profile.bass_gain, 0.44),
                PIANO_CHANNEL: (
                    paths.instrument(profile.comp),
                    profile.comp_gain,
                    0.38,
                ),
                FLUTE_CHANNEL: (
                    paths.instrument(profile.fill),
                    profile.fill_gain,
                    0.68,
                ),
                CELLO_CHANNEL: (paths.instrument(profile.pad), profile.pad_gain, 0.30),
                DRUM_CHANNEL: (
                    paths.instrument(profile.drums),
                    profile.drums_gain,
                    0.53,
                ),
            },
            voice_factory=voice_factory,
        )


class SfzStyleArrangementRenderer(SoundFontArrangementRenderer):
    """A built-in arrangement rendered through its open-sample genre profile."""

    def __init__(
        self,
        style_id: str,
        config: DemoAudioConfig,
        paths: SfzStylePaths,
        *,
        engine_factory: Callable[
            [DemoAudioConfig, SfzStylePaths, StyleSfzProfile], SynthEngine
        ] = SfzStyleRackEngine,
    ) -> None:
        try:
            profile = STYLE_SFZ_PROFILES[style_id]
        except KeyError as error:
            raise SfzError(f"style has no open-sample profile: {style_id}") from error
        super().__init__(
            style_id,
            config,
            "explicit SFZ genre rack",
            engine_factory=lambda renderer_config, _unused: engine_factory(
                renderer_config, paths, profile
            ),
        )
        self._attack_counts: dict[tuple[int, int], int] = {}

    def _configure_palette(self, palette: SoundFontPalette) -> None:
        self._engine.set_gain(STYLE_SFZ_MASTER_GAINS[self._definition.id])
        for channel, pan, volume in (
            (BASS_CHANNEL, 56, 108),
            (PIANO_CHANNEL, 43, 102),
            (FLUTE_CHANNEL, 84, 88),
            (CELLO_CHANNEL, 46, 82),
            (DRUM_CHANNEL, 66, 98),
        ):
            self._engine.control_change(channel, 10, pan)
            self._engine.control_change(channel, 7, volume)

    def _queue_style_events(
        self, start_beat: float, end_beat: float, chord: ChordState
    ) -> None:
        self._attack_counts.clear()
        super()._queue_style_events(start_beat, end_beat, chord)

    def _queue_at_beat(
        self,
        beat: float,
        start_beat: float,
        end_beat: float,
        channel: int,
        note: int,
        velocity: int,
        duration_beats: float,
    ) -> None:
        if velocity <= 0 or not start_beat <= beat < end_beat:
            return
        attack_seconds = {
            PIANO_CHANNEL: 0.006,
            FLUTE_CHANNEL: 0.003,
            CELLO_CHANNEL: 0.009,
        }.get(channel)
        if attack_seconds is not None:
            key = (round(beat * 1_000_000), channel)
            voice = self._attack_counts.get(key, 0)
            self._attack_counts[key] = voice + 1
            beat += voice * attack_seconds * self._tempo_bpm / 60
            velocity = max(1, velocity - (voice * 2))
            end_beat = max(end_beat, beat + 1e-9)
        super()._queue_at_beat(
            beat,
            start_beat,
            end_beat,
            channel,
            note,
            velocity,
            duration_beats,
        )


class SfzWaltzArrangementRenderer(SoundFontArrangementRenderer):
    """Classic Waltz with dedicated instruments and orchestral voice leading."""

    def __init__(
        self,
        config: DemoAudioConfig,
        paths: SfzWaltzPaths,
        *,
        engine_factory: Callable[
            [DemoAudioConfig, SfzWaltzPaths], SynthEngine
        ] = SfzWaltzRackEngine,
    ) -> None:
        super().__init__(
            "classic_waltz",
            config,
            "explicit SFZ rack",
            engine_factory=lambda renderer_config, _unused: engine_factory(
                renderer_config, paths
            ),
        )

    def _configure_palette(self, palette: SoundFontPalette) -> None:
        self._engine.set_gain(2.40)
        for channel, pan, volume in (
            (BASS_CHANNEL, 51, 112),
            (PIANO_CHANNEL, 60, 108),
            (FLUTE_CHANNEL, 88, 92),
            (CELLO_CHANNEL, 42, 94),
            (VIOLIN_CHANNEL, 86, 90),
            (DRUM_CHANNEL, 68, 96),
        ):
            self._engine.control_change(channel, 10, pan)
            self._engine.control_change(channel, 7, volume)

    def _queue_groove_bar(
        self,
        bar_beat: float,
        start_beat: float,
        end_beat: float,
        chord: ChordState,
        groove: GrooveBar,
        levels: EnsembleLevels,
        dynamic: float,
        final_bar: bool,
    ) -> None:
        intervals = self._INTERVALS[chord.quality]
        for pulse, (onset, interval) in enumerate(
            zip(groove.bass_onsets, groove.bass_intervals, strict=True)
        ):
            bass_root = (
                chord.bass_pitch_class
                if pulse == 0 and chord.bass_pitch_class is not None
                else chord.root_pitch_class
            )
            if groove.bass_roles:
                interval = self._renderer_type._bass_role_interval(
                    chord.quality, groove.bass_roles[pulse]
                )
            self._queue_at_beat(
                bar_beat + onset,
                start_beat,
                end_beat,
                BASS_CHANNEL,
                BASS_C_NOTE + bass_root + interval,
                self._velocity(
                    92,
                    levels.bass,
                    dynamic * self._accent(groove.bass_accents, pulse),
                ),
                0.78,
            )

        chord_onsets = (
            self._renderer_type._FINAL_CHORD_ONSETS
            if final_bar
            else groove.chord_onsets
        )
        for pulse, onset in enumerate(chord_onsets):
            rotation = pulse + groove.voicing_rotation
            voicing = tuple(
                intervals[(rotation + voice) % len(intervals)]
                + (12 if rotation + voice >= len(intervals) else 0)
                for voice in range(min(3, len(intervals)))
            )
            duration = (
                self._renderer_type.BEATS_PER_BAR - onset - 0.05
                if final_bar and pulse == len(chord_onsets) - 1
                else 0.52
            )
            for voice, interval in enumerate(voicing):
                self._queue_at_beat(
                    bar_beat + onset + (0.012 * voice),
                    start_beat,
                    end_beat,
                    PIANO_CHANNEL,
                    MIDDLE_C_NOTE + chord.root_pitch_class + interval,
                    self._velocity(
                        76 - (voice * 3),
                        levels.piano,
                        dynamic * self._accent(groove.chord_accents, pulse),
                    ),
                    duration - (0.018 * voice),
                )

        reed_onsets = groove.reed_onsets or ()
        for pulse, onset in enumerate(reed_onsets):
            melody_interval = intervals[
                (groove.voicing_rotation + pulse + 2) % len(intervals)
            ]
            self._queue_at_beat(
                bar_beat + onset + 0.008,
                start_beat,
                end_beat,
                FLUTE_CHANNEL,
                UPPER_C_NOTE + chord.root_pitch_class + melody_interval,
                self._velocity(
                    70,
                    levels.bandoneon,
                    dynamic * self._accent(groove.reed_accents, pulse),
                ),
                0.70,
            )

        for onset in groove.pad_onsets or ():
            cello_intervals = (intervals[0], intervals[-1])
            for voice, interval in enumerate(cello_intervals):
                self._queue_at_beat(
                    bar_beat + onset + (0.010 * voice),
                    start_beat,
                    end_beat,
                    CELLO_CHANNEL,
                    LOW_C_NOTE + chord.root_pitch_class + interval,
                    self._velocity(52 - (voice * 4), levels.strings, dynamic),
                    2.86 - (0.02 * voice),
                )
            violin_interval = intervals[1] if len(intervals) > 1 else intervals[0]
            self._queue_at_beat(
                bar_beat + onset + 0.018,
                start_beat,
                end_beat,
                VIOLIN_CHANNEL,
                UPPER_C_NOTE + chord.root_pitch_class + violin_interval,
                self._velocity(48, levels.strings, dynamic),
                2.82,
            )

        for pulse, onset in enumerate(groove.kick_onsets):
            self._queue_drum(
                bar_beat + onset,
                start_beat,
                end_beat,
                KICK_NOTE,
                self._velocity(
                    90,
                    levels.drums,
                    dynamic * self._accent(groove.kick_accents, pulse),
                ),
            )
        for pulse, onset in enumerate(groove.snare_onsets):
            self._queue_drum(
                bar_beat + onset + 0.006,
                start_beat,
                end_beat,
                self._palette.snare_note,
                self._velocity(
                    76,
                    levels.drums,
                    dynamic * self._accent(groove.snare_accents, pulse),
                ),
            )
        for pulse, onset in enumerate(groove.auxiliary_onsets):
            self._queue_drum(
                bar_beat + onset + 0.011,
                start_beat,
                end_beat,
                self._palette.auxiliary_note,
                self._velocity(
                    64,
                    levels.percussion,
                    dynamic * self._accent(groove.auxiliary_accents, pulse),
                ),
            )

    def _change_harmony(self, chord: ChordState, frame: int) -> None:
        for channel in WALTZ_MELODIC_CHANNELS:
            self._engine.control_change(channel, 120, 0)
        self._events = [
            event for event in self._events if event.channel == DRUM_CHANNEL
        ]
        heapq.heapify(self._events)
        intervals = self._INTERVALS[chord.quality]
        for voice, interval in enumerate(intervals[:3]):
            self._event_order += 1
            heapq.heappush(
                self._events,
                _SynthEvent(
                    frame + round(self._config.sample_rate * 0.008 * voice),
                    self._event_order,
                    PIANO_CHANNEL,
                    MIDDLE_C_NOTE + chord.root_pitch_class + interval,
                    48 - (voice * 2),
                    round(0.20 * 60 * self._config.sample_rate / self._tempo_bpm),
                ),
            )

    def _all_sound_off(self) -> None:
        for channel in (*WALTZ_MELODIC_CHANNELS, DRUM_CHANNEL):
            self._engine.control_change(channel, 120, 0)
        self._events.clear()
        self._silent = True
