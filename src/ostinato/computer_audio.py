"""Small computer-only arranger and PCM synthesizer for the audible POC.

This module intentionally consumes normalized chord states.  It does not model,
infer, or validate anything about the FR-4X MIDI implementation.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
import threading
from array import array
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from typing import IO, ClassVar, Protocol, TextIO

from ostinato.domain import ChordQuality, ChordState
from ostinato.keyboard_input import (
    MAX_TEMPO_BPM,
    MIN_TEMPO_BPM,
    KeyboardEvent,
    KeyboardEventKind,
    run_keyboard,
)

BASS_ROLES = {
    "root",
    "third",
    "fifth",
    "color",
    "octave",
}
BASS_C_NOTE = 36
LOW_C_NOTE = 48
MIDDLE_C_NOTE = 60
UPPER_C_NOTE = 72
TRANSPORT_TICKS_PER_BEAT = 96


class AudioPlaybackError(RuntimeError):
    """Raised when the host PCM player cannot be started or stops unexpectedly."""


class PcmSink(Protocol):
    """Destination for signed 16-bit, little-endian, stereo PCM."""

    def write(self, pcm: bytes) -> None:
        """Write one contiguous audio buffer."""

    def close(self) -> None:
        """Release the destination."""


class ArrangementRenderer(Protocol):
    """Renderer contract shared by procedural and sampled accompaniment."""

    @property
    def tempo_bpm(self) -> int: ...

    @property
    def section(self) -> DemoSection: ...

    @property
    def position_ticks(self) -> int: ...

    def set_tempo(self, tempo_bpm: int) -> None: ...

    def reset(self) -> None: ...

    def start_main(self) -> None: ...

    def stop(self) -> None: ...

    def start_intro(self) -> None: ...

    def request_ending(self) -> None: ...

    def resume_if_stopped(self) -> None: ...

    def render(self, frame_count: int, chord: ChordState | None) -> bytes: ...


@dataclass(frozen=True, slots=True)
class DemoAudioConfig:
    """Audio and tempo settings for the built-in demonstration arrangement."""

    tempo_bpm: int = 120
    sample_rate: int = 48_000
    chunk_frames: int = 480

    def __post_init__(self) -> None:
        if not MIN_TEMPO_BPM <= self.tempo_bpm <= MAX_TEMPO_BPM:
            raise ValueError(
                f"tempo_bpm must be between {MIN_TEMPO_BPM} and {MAX_TEMPO_BPM}"
            )
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self.chunk_frames <= 0:
            raise ValueError("chunk_frames must be positive")


class DemoSection(StrEnum):
    """Musical sections available in the computer-only demonstration."""

    INTRO = "intro"
    MAIN = "main"
    ENDING = "ending"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class EnsembleLevels:
    """Per-instrument mix levels for one orchestration stage."""

    bass: float
    piano: float
    bandoneon: float
    drums: float
    percussion: float
    strings: float


@dataclass(frozen=True, slots=True)
class GrooveBar:
    """One bar of original bass, comping, and percussion instructions."""

    bass_onsets: tuple[float, ...]
    bass_intervals: tuple[int, ...]
    chord_onsets: tuple[float, ...]
    kick_onsets: tuple[float, ...]
    snare_onsets: tuple[float, ...]
    auxiliary_onsets: tuple[float, ...]
    shaker_accents: tuple[int, ...]
    voicing_rotation: int = 0
    bass_roles: tuple[str, ...] = ()
    bass_accents: tuple[float, ...] = ()
    chord_accents: tuple[float, ...] = ()
    reed_onsets: tuple[float, ...] | None = None
    reed_accents: tuple[float, ...] = ()
    pad_onsets: tuple[float, ...] | None = None
    hat_onsets: tuple[float, ...] | None = None
    hat_accents: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not self.bass_onsets or len(self.bass_onsets) != len(self.bass_intervals):
            raise ValueError("bass onsets and intervals must be non-empty and aligned")
        for values, label in (
            (self.bass_roles, "bass roles"),
            (self.bass_accents, "bass accents"),
        ):
            if values and len(values) != len(self.bass_onsets):
                raise ValueError(f"{label} must align with bass onsets")
        if any(role not in BASS_ROLES for role in self.bass_roles):
            raise ValueError("bass roles contain an unsupported harmonic function")
        if self.chord_accents and len(self.chord_accents) != len(self.chord_onsets):
            raise ValueError("chord accents must align with chord onsets")
        if self.reed_accents and (
            self.reed_onsets is None or len(self.reed_accents) != len(self.reed_onsets)
        ):
            raise ValueError("reed accents must align with explicit reed onsets")
        if self.hat_accents and (
            self.hat_onsets is None or len(self.hat_accents) != len(self.hat_onsets)
        ):
            raise ValueError("hat accents must align with explicit hat onsets")
        for onsets in (
            self.bass_onsets,
            self.chord_onsets,
            self.kick_onsets,
            self.snare_onsets,
            self.auxiliary_onsets,
            self.reed_onsets or (),
            self.pad_onsets or (),
            self.hat_onsets or (),
        ):
            if any(onset < 0 for onset in onsets):
                raise ValueError("groove onsets cannot be negative")


class DemoArrangementRenderer:
    """Render an original modern-tango loop without external samples."""

    STYLE_NAME: ClassVar[str] = "modern_tango"
    DISPLAY_NAME: ClassVar[str] = "Modern Tango"
    DESCRIPTION: ClassVar[str] = "Dramatic 3+3+2 tango with piano, reeds, and strings"
    DEFAULT_TEMPO_BPM: ClassVar[int] = 120
    OUTPUT_MODE: ClassVar[str] = "procedural_pcm"
    MASTER_GAIN: ClassVar[float] = 2.6
    OUTPUT_LIMIT: ClassVar[int] = 30_000
    BEATS_PER_BAR: ClassVar[float] = 4.0
    SYNCOPATION_GROUPS: ClassVar[tuple[float, ...]] = (1.5, 1.5, 1.0)
    _BASS_DURATION_BEATS: ClassVar[float] = 0.42
    _CHORD_DURATION_BEATS: ClassVar[float] = 0.30
    _REED_DURATION_BEATS: ClassVar[float] = 0.26
    _PAD_DURATION_BEATS: ClassVar[float | None] = None

    _INTERVALS: ClassVar[dict[ChordQuality, tuple[int, ...]]] = {
        ChordQuality.MAJOR: (0, 4, 7),
        ChordQuality.MINOR: (0, 3, 7),
        ChordQuality.DOMINANT_SEVENTH: (0, 4, 7, 10),
        ChordQuality.DIMINISHED: (0, 3, 6),
    }
    _BASS_ONSETS: ClassVar[tuple[float, ...]] = (0.0, 1.5, 3.0)
    _BASS_INTERVALS: ClassVar[tuple[int, ...]] = (0, 7, 12)
    _CHORD_ONSETS: ClassVar[tuple[float, ...]] = (0.5, 2.0, 3.5)
    _FINAL_CHORD_ONSETS: ClassVar[tuple[float, ...]] = (0.0, 1.5, 3.0)
    _AUX_CLICK_ONSETS: ClassVar[tuple[float, ...]] = (0.75, 2.25, 3.75)
    _SHAKER_ACCENT_STEPS: ClassVar[tuple[int, ...]] = (0, 6, 12)
    _GROOVE: ClassVar[tuple[GrooveBar, ...]] = (
        GrooveBar(
            (0.0, 1.5, 3.0),
            (0, 7, 12),
            (0.5, 2.0, 3.5),
            (0.0, 1.5, 3.0),
            (0.5, 2.0, 3.5),
            (0.75, 2.25, 3.75),
            (0, 6, 12),
            0,
            bass_roles=("root", "fifth", "octave"),
            bass_accents=(1.12, 0.90, 1.02),
            chord_accents=(1.08, 0.88, 1.0),
            reed_onsets=(0.0, 3.0),
            reed_accents=(1.0, 0.88),
            pad_onsets=(0.0,),
            hat_onsets=(0.0, 1.5, 3.0),
            hat_accents=(1.0, 0.80, 0.90),
        ),
        GrooveBar(
            (0.0, 1.5, 3.0),
            (0, 12, 7),
            (0.5, 2.0, 3.5),
            (0.0, 1.5, 3.0),
            (0.5, 2.0, 3.5),
            (0.75, 2.25, 3.75),
            (0, 6, 12),
            1,
            bass_roles=("root", "octave", "fifth"),
            bass_accents=(1.08, 0.92, 1.0),
            chord_accents=(1.0, 0.86, 0.96),
            reed_onsets=(1.5,),
            reed_accents=(0.82,),
            pad_onsets=(0.0,),
            hat_onsets=(0.0, 1.5, 3.0),
            hat_accents=(1.0, 0.78, 0.88),
        ),
        GrooveBar(
            (0.0, 1.5, 3.0),
            (0, 7, 12),
            (0.5, 2.0, 3.5),
            (0.0, 1.5, 3.0),
            (0.5, 2.0, 3.5),
            (0.75, 2.25, 3.75),
            (0, 6, 12),
            2,
            bass_roles=("root", "fifth", "octave"),
            bass_accents=(1.14, 0.88, 1.04),
            chord_accents=(1.04, 0.84, 1.02),
            reed_onsets=(0.0, 2.0),
            reed_accents=(0.92, 0.82),
            pad_onsets=(0.0,),
            hat_onsets=(0.0, 1.5, 3.0),
            hat_accents=(1.0, 0.80, 0.92),
        ),
        GrooveBar(
            (0.0, 1.5, 3.0, 3.75),
            (0, 7, 12, 0),
            (0.5, 2.0, 3.0, 3.5),
            (0.0, 1.5, 3.0),
            (0.5, 2.0, 3.5),
            (0.75, 2.25, 3.25, 3.75),
            (0, 6, 12, 15),
            1,
            bass_roles=("root", "fifth", "octave", "root"),
            bass_accents=(1.16, 0.92, 1.05, 0.72),
            chord_accents=(1.02, 0.86, 0.78, 1.0),
            reed_onsets=(2.0, 3.0, 3.5),
            reed_accents=(0.72, 0.88, 1.0),
            pad_onsets=(0.0,),
            hat_onsets=(0.0, 1.5, 3.0, 3.75),
            hat_accents=(1.0, 0.80, 0.92, 0.68),
        ),
    )
    _PHRASE_DYNAMICS: ClassVar[tuple[float, ...]] = (0.92, 0.98, 1.03, 1.10)
    _SECTION_LENGTH_BEATS: ClassVar[float] = 16.0
    _MAIN_LEVELS: ClassVar[EnsembleLevels] = EnsembleLevels(
        bass=1.0,
        piano=0.82,
        bandoneon=1.0,
        drums=0.85,
        percussion=0.75,
        strings=0.65,
    )
    _INTRO_LEVELS: ClassVar[tuple[EnsembleLevels, ...]] = (
        EnsembleLevels(0.0, 0.0, 0.22, 0.0, 0.18, 0.78),
        EnsembleLevels(0.42, 0.48, 0.38, 0.12, 0.42, 0.85),
        EnsembleLevels(0.75, 0.68, 0.72, 0.50, 0.68, 0.78),
        EnsembleLevels(0.95, 0.80, 0.95, 0.80, 0.74, 0.68),
    )
    _ENDING_LEVELS: ClassVar[tuple[EnsembleLevels, ...]] = (
        EnsembleLevels(1.0, 0.82, 1.0, 0.85, 0.75, 0.68),
        EnsembleLevels(1.0, 0.92, 1.08, 0.68, 0.62, 0.82),
        EnsembleLevels(0.82, 1.0, 1.10, 0.36, 0.40, 1.0),
        EnsembleLevels(0.90, 0.88, 1.12, 0.22, 0.22, 1.12),
    )

    def __init__(self, config: DemoAudioConfig) -> None:
        self._config = config
        self._frame_position = 0
        self._tempo_bpm = config.tempo_bpm
        self._tempo_epoch_frame = 0
        self._tempo_epoch_beat = 0.0
        self._section = DemoSection.MAIN
        self._section_start_beat = 0.0
        self._ending_at_beat: float | None = None

    @property
    def frame_position(self) -> int:
        """Return the absolute render position used as the transport epoch."""

        return self._frame_position

    @property
    def tempo_bpm(self) -> int:
        """Return the tempo used for subsequently rendered frames."""

        return self._tempo_bpm

    @property
    def beat_position(self) -> float:
        """Return the continuous musical position at the next audio frame."""

        return self._beat_at_frame(self._frame_position)

    @property
    def position_ticks(self) -> int:
        """Return the rendered transport position as integer musical ticks."""

        return round(self.beat_position * TRANSPORT_TICKS_PER_BEAT)

    @property
    def section(self) -> DemoSection:
        """Return the currently active demonstration section."""

        self._advance_section(self.beat_position)
        return self._section

    def set_tempo(self, tempo_bpm: int) -> None:
        """Change tempo at the current frame without jumping musical position."""

        if not MIN_TEMPO_BPM <= tempo_bpm <= MAX_TEMPO_BPM:
            raise ValueError(
                f"tempo_bpm must be between {MIN_TEMPO_BPM} and {MAX_TEMPO_BPM}"
            )
        current_beat = self.beat_position
        self._tempo_epoch_frame = self._frame_position
        self._tempo_epoch_beat = current_beat
        self._tempo_bpm = tempo_bpm

    def reset(self) -> None:
        """Return the demonstration transport to the start of the main phrase."""

        self._frame_position = 0
        self._tempo_epoch_frame = 0
        self._tempo_epoch_beat = 0.0
        self._section = DemoSection.MAIN
        self._section_start_beat = 0.0
        self._ending_at_beat = None

    def start_main(self) -> None:
        """Restart the main pattern from its first bar."""

        self.reset()

    def stop(self) -> None:
        """Silence the arrangement without discarding the selected harmony."""

        self._section = DemoSection.STOPPED
        self._ending_at_beat = None

    def start_intro(self) -> None:
        """Restart with the original four-measure introduction."""

        self.reset()
        self._section = DemoSection.INTRO

    def request_ending(self) -> None:
        """Arm the original four-measure ending for the next bar boundary."""

        if self._section is DemoSection.STOPPED:
            return
        current_beat = self.beat_position
        bar = math.floor(current_beat / self.BEATS_PER_BAR) + 1
        self._ending_at_beat = bar * self.BEATS_PER_BAR

    def resume_if_stopped(self) -> None:
        """Start a fresh main phrase if a prior ending has completed."""

        if self.section is DemoSection.STOPPED:
            self.reset()

    def render(self, frame_count: int, chord: ChordState | None) -> bytes:
        """Render a buffer and advance by exactly ``frame_count`` samples."""

        if frame_count < 0:
            raise ValueError("frame_count cannot be negative")
        samples = array("h")
        for frame in range(self._frame_position, self._frame_position + frame_count):
            left, right = (
                (0.0, 0.0) if chord is None else self._render_frame(frame, chord)
            )
            left_sample = round(math.tanh(left * self.MASTER_GAIN) * self.OUTPUT_LIMIT)
            right_sample = round(
                math.tanh(right * self.MASTER_GAIN) * self.OUTPUT_LIMIT
            )
            samples.extend((left_sample, right_sample))
        self._frame_position += frame_count
        self._advance_section(self.beat_position)
        if sys.byteorder != "little":
            samples.byteswap()
        return samples.tobytes()

    def _render_frame(self, frame: int, chord: ChordState) -> tuple[float, float]:
        beat = self._beat_at_frame(frame)
        section, section_beat = self._advance_section(beat)
        if section is DemoSection.STOPPED:
            return 0.0, 0.0
        bar_phase = section_beat % self.BEATS_PER_BAR
        bar_index = math.floor(section_beat / self.BEATS_PER_BAR)
        groove = self._GROOVE[bar_index % len(self._GROOVE)]
        seconds_per_beat = 60 / self._tempo_bpm
        levels = self._ensemble_levels(section, section_beat)

        drums = self._render_drums(
            frame=frame,
            bar_phase=bar_phase,
            seconds_per_beat=seconds_per_beat,
            groove=groove,
        )
        percussion = self._render_auxiliary_percussion(
            frame=frame,
            pattern_beat=section_beat,
            bar_phase=bar_phase,
            seconds_per_beat=seconds_per_beat,
            groove=groove,
        )
        bass = self._render_bass(
            chord=chord,
            bar_phase=bar_phase,
            seconds_per_beat=seconds_per_beat,
            groove=groove,
        )
        piano = self._render_piano(
            chord=chord,
            bar_phase=bar_phase,
            seconds_per_beat=seconds_per_beat,
            groove=groove,
        )
        final_ending_bar = (
            section is DemoSection.ENDING
            and section_beat >= self._SECTION_LENGTH_BEATS - self.BEATS_PER_BAR
        )
        bandoneon = self._render_bandoneon(
            chord=chord,
            bar_phase=bar_phase,
            seconds_per_beat=seconds_per_beat,
            final_ending_bar=final_ending_bar,
            groove=groove,
        )
        strings = self._render_strings(
            frame=frame,
            chord=chord,
            bar_phase=bar_phase,
            final_ending_bar=final_ending_bar,
        )

        phrase_dynamic = self._PHRASE_DYNAMICS[bar_index % len(self._PHRASE_DYNAMICS)]
        left = right = 0.0
        for value, level, pan in (
            (bass, levels.bass, -0.08),
            (piano, levels.piano, -0.48),
            (bandoneon, levels.bandoneon, 0.34),
            (drums, levels.drums, -0.06),
            (percussion, levels.percussion, 0.56),
            (strings, levels.strings, -0.25),
        ):
            part_left, part_right = self._pan(value * level, pan)
            left += part_left
            right += part_right
        left *= phrase_dynamic
        right *= phrase_dynamic
        fade_start = self._SECTION_LENGTH_BEATS - 0.5
        if section is DemoSection.ENDING and section_beat > fade_start:
            remaining = self._SECTION_LENGTH_BEATS - section_beat
            fade = max(0.0, remaining / 0.5)
            left *= fade
            right *= fade
        return left, right

    def _render_bass(
        self,
        *,
        chord: ChordState,
        bar_phase: float,
        seconds_per_beat: float,
        groove: GrooveBar,
    ) -> float:
        pulse, elapsed_beats = self._pulse_at(bar_phase, groove.bass_onsets)
        bass_pitch_class = (
            chord.bass_pitch_class
            if pulse == 0 and chord.bass_pitch_class is not None
            else chord.root_pitch_class
        )
        elapsed_seconds = elapsed_beats * seconds_per_beat
        interval = groove.bass_intervals[pulse]
        if groove.bass_roles:
            interval = self._bass_role_interval(chord.quality, groove.bass_roles[pulse])
        note = BASS_C_NOTE + bass_pitch_class + interval
        frequency = self._midi_frequency(note)
        attack = min(1.0, elapsed_seconds * 90)
        envelope = attack * math.exp(-elapsed_seconds * 6.8)
        return (
            0.25
            * envelope
            * (
                math.sin(math.tau * frequency * elapsed_seconds)
                + (0.18 * math.sin(math.tau * frequency * 2 * elapsed_seconds))
            )
        )

    def _render_piano(
        self,
        *,
        chord: ChordState,
        bar_phase: float,
        seconds_per_beat: float,
        groove: GrooveBar,
    ) -> float:
        pulse, elapsed_beats = self._pulse_at(bar_phase, groove.chord_onsets)
        elapsed_seconds = elapsed_beats * seconds_per_beat
        attack = min(1.0, elapsed_seconds * 110)
        envelope = attack * math.exp(-elapsed_seconds * 8.5)
        intervals = self._INTERVALS[chord.quality]
        rotation = pulse + groove.voicing_rotation
        selected = tuple(
            intervals[(rotation + voice) % len(intervals)]
            + (12 if rotation + voice >= len(intervals) else 0)
            for voice in range(min(3, len(intervals)))
        )
        piano = 0.0
        for interval in selected:
            frequency = self._midi_frequency(
                MIDDLE_C_NOTE + chord.root_pitch_class + interval
            )
            piano += (
                math.sin(math.tau * frequency * elapsed_seconds)
                + (0.22 * math.sin(math.tau * frequency * 2 * elapsed_seconds))
                + (0.06 * math.sin(math.tau * frequency * 3 * elapsed_seconds))
            )
        return 0.09 * envelope * piano / len(selected)

    def _render_bandoneon(
        self,
        *,
        chord: ChordState,
        bar_phase: float,
        seconds_per_beat: float,
        final_ending_bar: bool,
        groove: GrooveBar,
    ) -> float:
        onsets = (
            self._FINAL_CHORD_ONSETS
            if final_ending_bar
            else (
                groove.reed_onsets
                if groove.reed_onsets is not None
                else groove.chord_onsets
            )
        )
        if not onsets:
            return 0.0
        _, elapsed_beats = self._pulse_at(bar_phase, onsets)
        elapsed_seconds = elapsed_beats * seconds_per_beat
        attack = min(1.0, elapsed_seconds * 100)
        final_accent = final_ending_bar and bar_phase >= self.BEATS_PER_BAR - 1.0
        decay = 3.0 if final_accent else 11
        envelope = attack * math.exp(-elapsed_seconds * decay)
        reed = 0.0
        intervals = self._INTERVALS[chord.quality]
        for interval in intervals:
            frequency = self._midi_frequency(
                MIDDLE_C_NOTE + chord.root_pitch_class + interval
            )
            reed += (
                math.sin(math.tau * frequency * elapsed_seconds)
                + (0.30 * math.sin(math.tau * frequency * 2 * elapsed_seconds))
                + (0.10 * math.sin(math.tau * frequency * 3 * elapsed_seconds))
            )
        return 0.15 * envelope * reed / len(intervals)

    def _render_strings(
        self,
        *,
        frame: int,
        chord: ChordState,
        bar_phase: float,
        final_ending_bar: bool,
    ) -> float:
        time_seconds = frame / self._config.sample_rate
        swell = 0.72 + (0.28 * math.sin(math.pi * bar_phase / self.BEATS_PER_BAR))
        if final_ending_bar and bar_phase >= 3.0:
            swell *= 1.18
        pad = 0.0
        intervals = self._INTERVALS[chord.quality]
        for interval in intervals:
            frequency = self._midi_frequency(
                UPPER_C_NOTE + chord.root_pitch_class + interval
            )
            pad += math.sin(math.tau * frequency * time_seconds) + (
                0.12 * math.sin(math.tau * frequency * 2 * time_seconds)
            )
        return 0.035 * swell * pad / len(intervals)

    def _render_drums(
        self,
        *,
        frame: int,
        bar_phase: float,
        seconds_per_beat: float,
        groove: GrooveBar,
    ) -> float:
        _, kick_elapsed_beats = self._pulse_at(bar_phase, groove.kick_onsets)
        kick_seconds = kick_elapsed_beats * seconds_per_beat
        kick_envelope = math.exp(-kick_seconds * 15)
        kick_cycles = (47 * kick_seconds) + (
            (70 / 30) * (1 - math.exp(-30 * kick_seconds))
        )
        kick = 0.25 * kick_envelope * math.sin(math.tau * kick_cycles)

        _, snare_elapsed_beats = self._pulse_at(bar_phase, groove.snare_onsets)
        snare_seconds = snare_elapsed_beats * seconds_per_beat
        snare_envelope = math.exp(-snare_seconds * 22)
        snare_noise = self._high_pass_noise(frame)
        snare_body = math.sin(math.tau * 175 * snare_seconds)
        snare = snare_envelope * ((0.075 * snare_noise) + (0.018 * snare_body))
        return kick + snare

    def _render_auxiliary_percussion(
        self,
        *,
        frame: int,
        pattern_beat: float,
        bar_phase: float,
        seconds_per_beat: float,
        groove: GrooveBar,
    ) -> float:
        _, click_elapsed_beats = self._pulse_at(bar_phase, groove.auxiliary_onsets)
        click_seconds = click_elapsed_beats * seconds_per_beat
        click_envelope = math.exp(-click_seconds * 46)
        click = (
            0.055
            * click_envelope
            * sum(
                math.sin(math.tau * frequency * click_seconds)
                for frequency in (1_450, 2_200, 3_100)
            )
            / 3
        )

        sixteenth = math.floor(pattern_beat * 4)
        sixteenth_phase = (pattern_beat * 4) - sixteenth
        shaker_seconds = sixteenth_phase * seconds_per_beat / 4
        shaker_envelope = math.exp(-shaker_seconds * 75)
        steps_per_bar = round(self.BEATS_PER_BAR * 4)
        shaker_accent = (
            1.5 if sixteenth % steps_per_bar in groove.shaker_accents else 0.65
        )
        shaker = 0.030 * shaker_accent * shaker_envelope * self._high_pass_noise(frame)
        return click + shaker

    @classmethod
    def _ensemble_levels(
        cls, section: DemoSection, section_beat: float
    ) -> EnsembleLevels:
        if section is DemoSection.MAIN:
            return cls._MAIN_LEVELS
        bar = min(
            len(cls._INTRO_LEVELS) - 1,
            math.floor(section_beat / cls.BEATS_PER_BAR),
        )
        if section is DemoSection.INTRO:
            return cls._INTRO_LEVELS[bar]
        if section is DemoSection.ENDING:
            return cls._ENDING_LEVELS[bar]
        return EnsembleLevels(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def _advance_section(self, beat: float) -> tuple[DemoSection, float]:
        if (
            self._ending_at_beat is not None
            and beat >= self._ending_at_beat
            and self._section is not DemoSection.STOPPED
        ):
            self._section = DemoSection.ENDING
            self._section_start_beat = self._ending_at_beat
            self._ending_at_beat = None

        section_beat = beat - self._section_start_beat
        if (
            self._section is DemoSection.INTRO
            and section_beat >= self._SECTION_LENGTH_BEATS
        ):
            self._section = DemoSection.MAIN
            self._section_start_beat += self._SECTION_LENGTH_BEATS
            section_beat = beat - self._section_start_beat
        elif (
            self._section is DemoSection.ENDING
            and section_beat >= self._SECTION_LENGTH_BEATS
        ):
            self._section = DemoSection.STOPPED
            section_beat = self._SECTION_LENGTH_BEATS
        return self._section, section_beat

    def _beat_at_frame(self, frame: int) -> float:
        elapsed_frames = frame - self._tempo_epoch_frame
        elapsed_beats = (
            elapsed_frames * self._tempo_bpm / (self._config.sample_rate * 60)
        )
        return self._tempo_epoch_beat + elapsed_beats

    @staticmethod
    def _midi_frequency(note: int) -> float:
        return 440.0 * math.pow(2.0, (note - 69) / 12)

    @staticmethod
    def _bass_role_interval(quality: ChordQuality, role: str) -> int:
        """Resolve a bass role without forcing major thirds on minor chords."""

        if role == "root":
            return 0
        if role == "third":
            return 3 if quality in (ChordQuality.MINOR, ChordQuality.DIMINISHED) else 4
        if role == "fifth":
            return 6 if quality is ChordQuality.DIMINISHED else 7
        if role == "color":
            return 10 if quality is ChordQuality.DOMINANT_SEVENTH else 12
        if role == "octave":
            return 12
        raise ValueError(f"unsupported bass role: {role}")

    @staticmethod
    def _pan(value: float, position: float) -> tuple[float, float]:
        """Place a mono voice in a restrained stereo field."""

        width = max(-1.0, min(1.0, position)) * 0.32
        return value * (1.0 - width), value * (1.0 + width)

    @classmethod
    def _high_pass_noise(cls, frame: int) -> float:
        return (cls._noise(frame) - cls._noise(frame - 1)) * 0.5

    @staticmethod
    def _noise(frame: int) -> float:
        """Return deterministic full-band noise without a repeating audio sample."""

        value = frame & 0xFFFFFFFF
        value ^= value >> 16
        value = (value * 0x7FEB352D) & 0xFFFFFFFF
        value ^= value >> 15
        value = (value * 0x846CA68B) & 0xFFFFFFFF
        value ^= value >> 16
        return (value / 2_147_483_647.5) - 1.0

    @classmethod
    def _pulse_at(cls, position: float, onsets: tuple[float, ...]) -> tuple[int, float]:
        """Return the most recent pulse index and elapsed beats in a 4/4 bar."""

        for index in range(len(onsets) - 1, -1, -1):
            onset = onsets[index]
            if position >= onset:
                return index, position - onset
        return len(onsets) - 1, position + (cls.BEATS_PER_BAR - onsets[-1])


class ClassicTangoRenderer(DemoArrangementRenderer):
    """Render a traditional dance tango built from marcato and sincopa."""

    STYLE_NAME = "classic_tango"
    DISPLAY_NAME = "Classic Tango"
    DESCRIPTION = "Traditional marcato tango with piano, bass, bandoneon, and strings"
    DEFAULT_TEMPO_BPM = 120
    BEATS_PER_BAR = 4.0
    SYNCOPATION_GROUPS = (1.0, 1.0, 1.0, 1.0)
    _FINAL_CHORD_ONSETS = (0.0, 2.0, 3.0)
    _BASS_DURATION_BEATS = 0.54
    _CHORD_DURATION_BEATS = 0.27
    _REED_DURATION_BEATS = 0.32
    _PAD_DURATION_BEATS = 0.28
    _GROOVE = (
        GrooveBar(
            (0.0, 1.0, 2.0, 3.0),
            (0, 7, 12, 7),
            (0.0, 1.0, 2.0, 3.0),
            (0.0,),
            (2.0,),
            (0.0,),
            (0,),
            0,
            bass_roles=("root", "fifth", "octave", "fifth"),
            bass_accents=(1.16, 0.78, 1.04, 0.76),
            chord_accents=(1.12, 0.74, 1.0, 0.72),
            reed_onsets=(0.0, 2.0),
            reed_accents=(0.82, 0.72),
            pad_onsets=(0.0, 1.0, 2.0, 3.0),
            hat_onsets=(),
        ),
        GrooveBar(
            (0.0, 2.0),
            (0, 7),
            (0.0, 2.0),
            (0.0,),
            (2.0,),
            (0.0,),
            (0,),
            1,
            bass_roles=("root", "fifth"),
            bass_accents=(1.16, 1.0),
            chord_accents=(1.10, 0.96),
            reed_onsets=(1.5, 3.5),
            reed_accents=(0.64, 0.72),
            pad_onsets=(0.0, 2.0),
            hat_onsets=(),
        ),
        GrooveBar(
            (0.0, 1.5, 2.0, 3.5),
            (0, 7, 12, 7),
            (0.0, 1.5, 2.0, 3.5),
            (0.0,),
            (2.0,),
            (0.0,),
            (0,),
            2,
            bass_roles=("root", "fifth", "octave", "fifth"),
            bass_accents=(1.12, 0.84, 1.04, 0.82),
            chord_accents=(1.08, 0.82, 1.0, 0.80),
            reed_onsets=(1.5, 3.5),
            reed_accents=(0.70, 0.76),
            pad_onsets=(0.0, 1.5, 2.0, 3.5),
            hat_onsets=(),
        ),
        GrooveBar(
            (0.0, 1.0, 2.0, 3.0, 3.5),
            (0, 7, 12, 7, 0),
            (0.0, 1.0, 2.0, 3.0),
            (0.0,),
            (2.0,),
            (0.0,),
            (0,),
            1,
            bass_roles=("root", "fifth", "octave", "fifth", "root"),
            bass_accents=(1.18, 0.76, 1.04, 0.74, 0.62),
            chord_accents=(1.12, 0.72, 1.0, 0.70),
            reed_onsets=(2.0, 3.0, 3.5),
            reed_accents=(0.64, 0.72, 0.78),
            pad_onsets=(0.0, 1.0, 2.0, 3.0),
            hat_onsets=(),
        ),
    )
    _PHRASE_DYNAMICS = (0.94, 0.98, 1.02, 1.08)
    _MAIN_LEVELS = EnsembleLevels(0.98, 0.98, 0.82, 0.0, 0.0, 0.78)
    _INTRO_LEVELS = (
        EnsembleLevels(0.0, 0.48, 0.52, 0.0, 0.0, 0.42),
        EnsembleLevels(0.48, 0.68, 0.62, 0.0, 0.0, 0.56),
        EnsembleLevels(0.74, 0.84, 0.72, 0.0, 0.0, 0.68),
        EnsembleLevels(0.94, 0.96, 0.80, 0.0, 0.0, 0.76),
    )
    _ENDING_LEVELS = (
        EnsembleLevels(1.0, 1.0, 0.84, 0.0, 0.0, 0.80),
        EnsembleLevels(0.96, 1.06, 0.92, 0.0, 0.0, 0.88),
        EnsembleLevels(0.86, 1.10, 1.0, 0.0, 0.0, 0.98),
        EnsembleLevels(0.82, 1.06, 1.06, 0.0, 0.0, 1.08),
    )


class ClassicWaltzRenderer(DemoArrangementRenderer):
    """Render an original orchestral three-beat dance pattern."""

    STYLE_NAME = "classic_waltz"
    DISPLAY_NAME = "Classic Waltz"
    DESCRIPTION = "Flowing orchestral waltz with true oom-pah-pah movement"
    DEFAULT_TEMPO_BPM = 96
    BEATS_PER_BAR = 3.0
    SYNCOPATION_GROUPS = (1.0, 1.0, 1.0)
    _BASS_ONSETS = (0.0,)
    _BASS_INTERVALS = (0,)
    _CHORD_ONSETS = (1.0, 2.0)
    _FINAL_CHORD_ONSETS = (0.0, 1.0, 2.0)
    _AUX_CLICK_ONSETS = (1.0, 2.0)
    _SHAKER_ACCENT_STEPS = (0, 4, 8)
    _BASS_DURATION_BEATS = 0.82
    _CHORD_DURATION_BEATS = 0.56
    _REED_DURATION_BEATS = 0.74
    _GROOVE = (
        GrooveBar(
            (0.0,),
            (0,),
            (1.0, 2.0),
            (0.0,),
            (1.0, 2.0),
            (1.0, 2.0),
            (0, 4, 8),
            0,
            bass_roles=("root",),
            bass_accents=(1.08,),
            chord_accents=(0.86, 0.72),
            reed_onsets=(0.0,),
            reed_accents=(0.66,),
            pad_onsets=(0.0,),
            hat_onsets=(),
        ),
        GrooveBar(
            (0.0,),
            (7,),
            (1.0, 2.0),
            (0.0,),
            (1.0, 2.0),
            (2.0,),
            (0, 8),
            1,
            bass_roles=("fifth",),
            bass_accents=(0.98,),
            chord_accents=(0.82, 0.68),
            reed_onsets=(),
            pad_onsets=(0.0,),
            hat_onsets=(),
        ),
        GrooveBar(
            (0.0,),
            (12,),
            (1.0, 2.0),
            (0.0,),
            (1.0, 2.0),
            (1.0, 2.0),
            (0, 4, 8),
            2,
            bass_roles=("octave",),
            bass_accents=(1.04,),
            chord_accents=(0.88, 0.72),
            reed_onsets=(0.0, 2.0),
            reed_accents=(0.58, 0.48),
            pad_onsets=(0.0,),
            hat_onsets=(),
        ),
        GrooveBar(
            (0.0, 2.5),
            (7, 0),
            (1.0, 2.0, 2.5),
            (0.0, 2.5),
            (1.0, 2.0, 2.5, 2.75),
            (1.0, 2.0, 2.5, 2.75),
            (0, 4, 8, 10, 11),
            1,
            bass_roles=("fifth", "root"),
            bass_accents=(1.0, 0.62),
            chord_accents=(0.88, 0.72, 0.64),
            reed_onsets=(2.0, 2.5),
            reed_accents=(0.56, 0.72),
            pad_onsets=(0.0,),
            hat_onsets=(),
        ),
    )
    _PHRASE_DYNAMICS = (0.88, 0.96, 1.02, 1.08)
    _SECTION_LENGTH_BEATS = 12.0
    _MAIN_LEVELS = EnsembleLevels(
        bass=0.82,
        piano=0.96,
        bandoneon=0.68,
        drums=0.48,
        percussion=0.52,
        strings=0.88,
    )
    _INTRO_LEVELS = (
        EnsembleLevels(0.0, 0.18, 0.18, 0.0, 0.0, 0.82),
        EnsembleLevels(0.34, 0.46, 0.30, 0.08, 0.20, 0.92),
        EnsembleLevels(0.62, 0.72, 0.50, 0.26, 0.38, 0.96),
        EnsembleLevels(0.80, 0.92, 0.66, 0.46, 0.50, 0.90),
    )
    _ENDING_LEVELS = (
        EnsembleLevels(0.84, 0.98, 0.72, 0.46, 0.50, 0.92),
        EnsembleLevels(0.82, 1.04, 0.84, 0.34, 0.38, 1.0),
        EnsembleLevels(0.72, 1.08, 0.94, 0.18, 0.22, 1.08),
        EnsembleLevels(0.78, 1.0, 1.04, 0.08, 0.08, 1.16),
    )


class BossaNovaRenderer(DemoArrangementRenderer):
    """Render a relaxed original bossa-nova accompaniment."""

    STYLE_NAME = "bossa_nova"
    DISPLAY_NAME = "Bossa Nova"
    DESCRIPTION = "Relaxed syncopated bossa with warm bass and brushed percussion"
    DEFAULT_TEMPO_BPM = 116
    BEATS_PER_BAR = 4.0
    SYNCOPATION_GROUPS = (1.0, 1.0, 1.0, 1.0)
    _FINAL_CHORD_ONSETS = (0.0, 2.0, 3.5)
    _BASS_DURATION_BEATS = 0.90
    _CHORD_DURATION_BEATS = 0.52
    _REED_DURATION_BEATS = 0.44
    _GROOVE = (
        GrooveBar(
            (0.0, 2.0),
            (0, 7),
            (0.0, 1.5, 3.0),
            (0.0, 2.0),
            (1.5, 3.5),
            (0.5, 1.5, 2.5, 3.5),
            (0, 3, 8, 11),
            0,
            bass_roles=("root", "fifth"),
            bass_accents=(0.94, 1.06),
            chord_accents=(0.78, 0.92, 0.82),
            reed_onsets=(),
            pad_onsets=(),
            hat_onsets=(0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5),
            hat_accents=(0.72, 0.46, 0.58, 0.48, 0.78, 0.46, 0.58, 0.52),
        ),
        GrooveBar(
            (0.0, 2.0),
            (0, 7),
            (0.5, 2.0, 3.5),
            (0.0, 2.0),
            (1.0, 3.0),
            (0.5, 1.5, 2.5, 3.5),
            (0, 4, 8, 13),
            1,
            bass_roles=("root", "fifth"),
            bass_accents=(0.92, 1.08),
            chord_accents=(0.80, 0.90, 0.76),
            reed_onsets=(),
            pad_onsets=(),
            hat_onsets=(0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5),
            hat_accents=(0.72, 0.46, 0.58, 0.48, 0.80, 0.46, 0.58, 0.52),
        ),
        GrooveBar(
            (0.0, 2.0),
            (0, 7),
            (0.0, 1.5, 2.5, 3.5),
            (0.0, 2.0),
            (1.5, 3.5),
            (0.5, 1.5, 2.5, 3.5),
            (0, 3, 8, 12),
            2,
            bass_roles=("root", "fifth"),
            bass_accents=(0.94, 1.08),
            chord_accents=(0.76, 0.90, 0.70, 0.82),
            reed_onsets=(3.5,),
            reed_accents=(0.46,),
            pad_onsets=(),
            hat_onsets=(0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5),
            hat_accents=(0.72, 0.46, 0.58, 0.48, 0.80, 0.46, 0.58, 0.52),
        ),
        GrooveBar(
            (0.0, 2.0, 3.5),
            (0, 7, 0),
            (0.5, 2.0, 3.0, 3.75),
            (0.0, 2.0),
            (1.0, 3.0),
            (0.5, 1.5, 2.5, 3.5),
            (0, 4, 8, 12, 14),
            1,
            bass_roles=("root", "fifth", "root"),
            bass_accents=(0.96, 1.08, 0.58),
            chord_accents=(0.78, 0.92, 0.70, 0.62),
            reed_onsets=(3.0, 3.75),
            reed_accents=(0.42, 0.54),
            pad_onsets=(),
            hat_onsets=(0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5),
            hat_accents=(0.72, 0.46, 0.58, 0.48, 0.82, 0.46, 0.62, 0.56),
        ),
    )
    _PHRASE_DYNAMICS = (0.88, 0.94, 0.98, 1.04)
    _MAIN_LEVELS = EnsembleLevels(0.84, 0.86, 0.48, 0.42, 0.76, 0.42)
    _INTRO_LEVELS = (
        EnsembleLevels(0.0, 0.32, 0.0, 0.0, 0.32, 0.30),
        EnsembleLevels(0.40, 0.54, 0.18, 0.10, 0.58, 0.34),
        EnsembleLevels(0.68, 0.72, 0.34, 0.28, 0.72, 0.38),
        EnsembleLevels(0.82, 0.84, 0.46, 0.40, 0.76, 0.42),
    )
    _ENDING_LEVELS = (
        EnsembleLevels(0.84, 0.86, 0.48, 0.42, 0.76, 0.42),
        EnsembleLevels(0.76, 0.92, 0.54, 0.30, 0.62, 0.48),
        EnsembleLevels(0.62, 0.96, 0.62, 0.18, 0.42, 0.56),
        EnsembleLevels(0.54, 0.90, 0.72, 0.08, 0.18, 0.66),
    )


class SwingFoxtrotRenderer(DemoArrangementRenderer):
    """Render an original small-combo swing foxtrot."""

    STYLE_NAME = "swing_foxtrot"
    DISPLAY_NAME = "Swing Foxtrot"
    DESCRIPTION = "Light swing with walking bass, offbeat comping, and ride pulse"
    DEFAULT_TEMPO_BPM = 132
    BEATS_PER_BAR = 4.0
    SYNCOPATION_GROUPS = (1.0, 1.0, 1.0, 1.0)
    _FINAL_CHORD_ONSETS = (0.0, 2.0, 3.0)
    _BASS_DURATION_BEATS = 0.86
    _CHORD_DURATION_BEATS = 0.24
    _REED_DURATION_BEATS = 0.48
    _GROOVE = (
        GrooveBar(
            (0.0, 1.0, 2.0, 3.0),
            (0, 4, 7, 11),
            (0.67, 2.67),
            (0.0, 2.0),
            (1.0, 3.0),
            (0.0, 2.0),
            (0, 8),
            0,
            bass_roles=("root", "third", "fifth", "color"),
            bass_accents=(1.04, 0.88, 0.96, 0.84),
            chord_accents=(0.78, 0.70),
            reed_onsets=(0.0, 2.0),
            reed_accents=(0.48, 0.42),
            pad_onsets=(0.0,),
            hat_onsets=(0.0, 0.67, 1.0, 2.0, 2.67, 3.0),
            hat_accents=(0.90, 0.58, 0.72, 0.84, 0.56, 0.70),
        ),
        GrooveBar(
            (0.0, 1.0, 2.0, 3.0),
            (12, 10, 7, 4),
            (1.67, 3.67),
            (0.0, 2.0),
            (1.0, 3.0),
            (0.0, 2.0),
            (0, 4, 8, 12),
            1,
            bass_roles=("octave", "color", "fifth", "third"),
            bass_accents=(1.0, 0.86, 0.94, 0.84),
            chord_accents=(0.74, 0.68),
            reed_onsets=(3.0, 3.67),
            reed_accents=(0.38, 0.52),
            pad_onsets=(0.0,),
            hat_onsets=(0.0, 0.67, 1.0, 2.0, 2.67, 3.0),
            hat_accents=(0.88, 0.56, 0.70, 0.84, 0.56, 0.70),
        ),
        GrooveBar(
            (0.0, 1.0, 2.0, 3.0),
            (0, 4, 7, 10),
            (0.67, 1.67, 3.67),
            (0.0, 2.0),
            (1.0, 3.0),
            (0.0, 2.0),
            (0, 3, 4, 8, 11, 12),
            2,
            bass_roles=("root", "third", "fifth", "color"),
            bass_accents=(1.04, 0.88, 0.96, 0.84),
            chord_accents=(0.76, 0.70, 0.66),
            reed_onsets=(0.0,),
            reed_accents=(0.44,),
            pad_onsets=(0.0,),
            hat_onsets=(0.0, 0.67, 1.0, 2.0, 2.67, 3.0),
            hat_accents=(0.90, 0.58, 0.72, 0.84, 0.56, 0.70),
        ),
        GrooveBar(
            (0.0, 1.0, 2.0, 3.0),
            (0, 4, 7, 11),
            (1.67, 2.67, 3.67),
            (0.0, 2.0),
            (1.0, 3.0, 3.67),
            (0.0, 2.0, 3.67),
            (0, 4, 8, 12, 15),
            1,
            bass_roles=("root", "third", "fifth", "color"),
            bass_accents=(1.04, 0.88, 0.96, 0.80),
            chord_accents=(0.72, 0.70, 0.78),
            reed_onsets=(2.67, 3.33, 3.67),
            reed_accents=(0.40, 0.48, 0.58),
            pad_onsets=(0.0,),
            hat_onsets=(0.0, 0.67, 1.0, 2.0, 2.67, 3.0, 3.67),
            hat_accents=(0.90, 0.58, 0.72, 0.84, 0.56, 0.70, 0.62),
        ),
    )
    _PHRASE_DYNAMICS = (0.90, 0.96, 1.0, 1.08)
    _MAIN_LEVELS = EnsembleLevels(0.92, 0.82, 0.60, 0.62, 0.68, 0.46)
    _INTRO_LEVELS = (
        EnsembleLevels(0.0, 0.42, 0.24, 0.0, 0.30, 0.18),
        EnsembleLevels(0.46, 0.58, 0.34, 0.24, 0.48, 0.24),
        EnsembleLevels(0.72, 0.70, 0.48, 0.46, 0.60, 0.34),
        EnsembleLevels(0.90, 0.80, 0.58, 0.60, 0.66, 0.44),
    )
    _ENDING_LEVELS = (
        EnsembleLevels(0.92, 0.82, 0.60, 0.62, 0.68, 0.46),
        EnsembleLevels(0.92, 0.90, 0.68, 0.52, 0.58, 0.54),
        EnsembleLevels(0.80, 0.98, 0.80, 0.32, 0.42, 0.66),
        EnsembleLevels(0.72, 0.92, 0.90, 0.14, 0.18, 0.80),
    )


class AlpinePolkaRenderer(DemoArrangementRenderer):
    """Render a bright original two-beat accordion polka."""

    STYLE_NAME = "alpine_polka"
    DISPLAY_NAME = "Alpine Polka"
    DESCRIPTION = "Bright two-step polka with alternating bass and lively fills"
    DEFAULT_TEMPO_BPM = 124
    BEATS_PER_BAR = 2.0
    SYNCOPATION_GROUPS = (1.0, 1.0)
    _FINAL_CHORD_ONSETS = (0.0, 1.0, 1.5)
    _SECTION_LENGTH_BEATS = 8.0
    _BASS_DURATION_BEATS = 0.36
    _CHORD_DURATION_BEATS = 0.28
    _REED_DURATION_BEATS = 0.24
    _GROOVE = (
        GrooveBar(
            (0.0, 1.0),
            (0, 7),
            (0.5, 1.5),
            (0.0, 1.0),
            (0.5, 1.5),
            (0.5, 1.5),
            (0, 4),
            0,
            bass_roles=("root", "fifth"),
            bass_accents=(1.08, 0.96),
            chord_accents=(0.88, 0.82),
            reed_onsets=(0.5, 1.5),
            reed_accents=(0.66, 0.60),
            pad_onsets=(),
            hat_onsets=(),
        ),
        GrooveBar(
            (0.0, 1.0),
            (12, 7),
            (0.5, 1.5),
            (0.0, 1.0),
            (0.5, 1.5),
            (0.5, 1.5),
            (0, 4, 6),
            1,
            bass_roles=("octave", "fifth"),
            bass_accents=(1.02, 0.94),
            chord_accents=(0.86, 0.80),
            reed_onsets=(0.5,),
            reed_accents=(0.60,),
            pad_onsets=(),
            hat_onsets=(),
        ),
        GrooveBar(
            (0.0, 1.0),
            (0, 12),
            (0.5, 1.5),
            (0.0, 1.0),
            (0.5, 1.5),
            (0.5, 1.5),
            (0, 2, 4),
            2,
            bass_roles=("root", "octave"),
            bass_accents=(1.08, 0.96),
            chord_accents=(0.90, 0.82),
            reed_onsets=(1.5,),
            reed_accents=(0.64,),
            pad_onsets=(),
            hat_onsets=(),
        ),
        GrooveBar(
            (0.0, 1.0, 1.75),
            (0, 7, 0),
            (0.5, 1.5, 1.75),
            (0.0, 1.0),
            (0.5, 1.5, 1.75),
            (0.5, 1.5, 1.75),
            (0, 4, 6, 7),
            1,
            bass_roles=("root", "fifth", "root"),
            bass_accents=(1.10, 0.96, 0.62),
            chord_accents=(0.90, 0.84, 0.64),
            reed_onsets=(1.25, 1.5, 1.75),
            reed_accents=(0.48, 0.56, 0.68),
            pad_onsets=(),
            hat_onsets=(),
        ),
    )
    _PHRASE_DYNAMICS = (0.94, 0.98, 1.02, 1.10)
    _MAIN_LEVELS = EnsembleLevels(1.0, 0.72, 1.02, 0.72, 0.70, 0.34)
    _INTRO_LEVELS = (
        EnsembleLevels(0.0, 0.0, 0.46, 0.0, 0.18, 0.18),
        EnsembleLevels(0.48, 0.34, 0.64, 0.20, 0.42, 0.22),
        EnsembleLevels(0.78, 0.54, 0.84, 0.48, 0.60, 0.28),
        EnsembleLevels(0.98, 0.70, 1.0, 0.70, 0.68, 0.34),
    )
    _ENDING_LEVELS = (
        EnsembleLevels(1.0, 0.72, 1.02, 0.72, 0.70, 0.34),
        EnsembleLevels(1.0, 0.80, 1.08, 0.62, 0.58, 0.42),
        EnsembleLevels(0.88, 0.88, 1.14, 0.40, 0.40, 0.52),
        EnsembleLevels(0.80, 0.82, 1.20, 0.18, 0.16, 0.64),
    )


@dataclass(frozen=True, slots=True)
class DemoStyleDefinition:
    """Public metadata and renderer type for one original procedural style."""

    id: str
    name: str
    description: str
    default_tempo_bpm: int
    beats_per_bar: int
    renderer: type[DemoArrangementRenderer]


DEMO_STYLES: dict[str, DemoStyleDefinition] = {
    renderer.STYLE_NAME: DemoStyleDefinition(
        id=renderer.STYLE_NAME,
        name=renderer.DISPLAY_NAME,
        description=renderer.DESCRIPTION,
        default_tempo_bpm=renderer.DEFAULT_TEMPO_BPM,
        beats_per_bar=round(renderer.BEATS_PER_BAR),
        renderer=renderer,
    )
    for renderer in (
        DemoArrangementRenderer,
        ClassicTangoRenderer,
        ClassicWaltzRenderer,
        BossaNovaRenderer,
        SwingFoxtrotRenderer,
        AlpinePolkaRenderer,
    )
}


def create_demo_renderer(
    style_id: str, config: DemoAudioConfig
) -> DemoArrangementRenderer:
    """Create the validated renderer for ``style_id``."""

    try:
        definition = DEMO_STYLES[style_id]
    except KeyError as error:
        raise ValueError(f"unknown arranger style: {style_id}") from error
    return definition.renderer(config)


class AplayPcmSink:
    """Stream PCM to one explicitly selected ALSA route through ``aplay``."""

    def __init__(self, config: DemoAudioConfig, *, device: str | None = None) -> None:
        executable = shutil.which("aplay")
        if executable is None:
            raise AudioPlaybackError(
                "aplay is not available; install ALSA utilities or run without --play"
            )
        command = [
            executable,
            "--quiet",
        ]
        if device is not None:
            command.extend(("--device", device))
        command.extend(
            [
                "--file-type=raw",
                "--format=S16_LE",
                "--channels=2",
                f"--rate={config.sample_rate}",
                "--period-time=10000",
                "--buffer-time=40000",
            ]
        )
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        if self._process.stdin is None:
            self._process.kill()
            raise AudioPlaybackError("aplay did not expose an audio input stream")
        self._input: IO[bytes] = self._process.stdin

    def write(self, pcm: bytes) -> None:
        """Write audio, surfacing an early player failure as an actionable error."""

        if self._process.poll() is not None:
            raise AudioPlaybackError(self._failure_detail())
        try:
            self._input.write(pcm)
        except OSError as error:
            raise AudioPlaybackError(self._failure_detail()) from error

    def close(self) -> None:
        """Close the stream and stop the child if its normal drain takes too long."""

        if not self._input.closed:
            with suppress(BrokenPipeError):
                self._input.close()
        forced_stop = False
        try:
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            forced_stop = True
            self._process.terminate()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=1)
        if not forced_stop and self._process.returncode not in (None, 0):
            raise AudioPlaybackError(self._failure_detail())

    def _failure_detail(self) -> str:
        stderr = self._process.stderr
        detail = stderr.read().decode(errors="replace").strip() if stderr else ""
        return f"aplay stopped unexpectedly{f': {detail}' if detail else ''}"


class PipewirePcmSink:
    """Stream PCM to one exact sink in the mounted host PipeWire session."""

    def __init__(self, config: DemoAudioConfig, *, target: str) -> None:
        executable = shutil.which("pw-cat")
        if executable is None:
            raise AudioPlaybackError("pw-cat is not available in the service container")
        if not target:
            raise AudioPlaybackError("PipeWire target cannot be empty")
        command = [
            executable,
            "--playback",
            "--target",
            target,
            "--rate",
            str(config.sample_rate),
            "--channels",
            "2",
            "--format",
            "s16",
            "--latency",
            "20ms",
            "-",
        ]
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        if self._process.stdin is None:
            self._process.kill()
            raise AudioPlaybackError("pw-cat did not expose an audio input stream")
        self._input: IO[bytes] = self._process.stdin

    def write(self, pcm: bytes) -> None:
        if self._process.poll() is not None:
            raise AudioPlaybackError(self._failure_detail())
        try:
            self._input.write(pcm)
        except OSError as error:
            raise AudioPlaybackError(self._failure_detail()) from error

    def close(self) -> None:
        if not self._input.closed:
            with suppress(BrokenPipeError):
                self._input.close()
        forced_stop = False
        try:
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            forced_stop = True
            self._process.terminate()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=1)
        if not forced_stop and self._process.returncode not in (None, 0):
            raise AudioPlaybackError(self._failure_detail())

    def _failure_detail(self) -> str:
        stderr = self._process.stderr
        detail = stderr.read().decode(errors="replace").strip() if stderr else ""
        return (
            f"PipeWire playback stopped unexpectedly{f': {detail}' if detail else ''}"
        )


def open_pcm_sink(config: DemoAudioConfig, device: str) -> PcmSink:
    """Open a validated PipeWire or direct ALSA output identifier."""

    pipewire_prefix = "pipewire:"
    if device.startswith(pipewire_prefix):
        return PipewirePcmSink(
            config,
            target=device.removeprefix(pipewire_prefix),
        )
    return AplayPcmSink(config, device=device)


class RealtimeDemoArranger:
    """Own the audio worker and apply explicit keyboard events to its chord state."""

    def __init__(
        self,
        config: DemoAudioConfig,
        sink: PcmSink,
        *,
        style_id: str = DemoArrangementRenderer.STYLE_NAME,
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
        renderer_factory: Callable[
            [str, DemoAudioConfig], ArrangementRenderer
        ] = create_demo_renderer,
    ) -> None:
        self._config = config
        self._sink = sink
        self._renderer_factory = renderer_factory
        self._renderer: ArrangementRenderer = renderer_factory(style_id, config)
        self._style_id = style_id
        self._thread_factory = thread_factory
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._chord: ChordState | None = None
        self._reset_requested = False
        self._tempo_requested: int | None = None
        self._resume_requested = False
        self._intro_requested = False
        self._ending_requested = False
        self._start_requested = False
        self._stop_playback_requested = False
        self._style_requested: str | None = None
        self._error: AudioPlaybackError | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Begin producing paced buffers for the PCM sink."""

        if self._thread is not None:
            raise RuntimeError("demo arranger is already started")
        self._thread = self._thread_factory(
            target=self._run,
            name="ostinato-demo-audio",
            daemon=True,
        )
        self._thread.start()

    def handle_event(self, event: KeyboardEvent) -> None:
        """Apply only the events that alter audible arranger state."""

        self._raise_worker_error()
        with self._lock:
            if event.kind is KeyboardEventKind.CHORD:
                self._chord = event.chord
                self._resume_requested = True
            elif event.kind is KeyboardEventKind.CLEAR:
                self._chord = None
            elif event.kind is KeyboardEventKind.PANIC:
                self._chord = None
                self._reset_requested = True
            elif event.kind is KeyboardEventKind.TEMPO:
                self._tempo_requested = event.tempo_bpm
            elif event.kind is KeyboardEventKind.INTRO:
                self._intro_requested = True
            elif event.kind is KeyboardEventKind.ENDING:
                self._ending_requested = True

    def set_chord(self, chord: ChordState | None, *, resume: bool = False) -> None:
        """Update harmony independently from the transport state."""

        self._raise_worker_error()
        with self._lock:
            self._chord = chord
            self._resume_requested = resume and chord is not None

    def set_tempo(self, tempo_bpm: int) -> None:
        """Request a continuous tempo change on the audio worker."""

        if not MIN_TEMPO_BPM <= tempo_bpm <= MAX_TEMPO_BPM:
            raise ValueError(
                f"tempo_bpm must be between {MIN_TEMPO_BPM} and {MAX_TEMPO_BPM}"
            )
        self._raise_worker_error()
        with self._lock:
            self._tempo_requested = tempo_bpm

    def start_main(self) -> None:
        """Start the selected style at the first main-pattern bar."""

        self._raise_worker_error()
        with self._lock:
            self._start_requested = True

    def start_intro(self) -> None:
        """Start the selected style at its introduction."""

        self._raise_worker_error()
        with self._lock:
            self._intro_requested = True

    def request_ending(self) -> None:
        """Arm the selected style's ending at its next bar boundary."""

        self._raise_worker_error()
        with self._lock:
            self._ending_requested = True

    def stop_playback(self) -> None:
        """Stop accompaniment while keeping the audio worker available."""

        self._raise_worker_error()
        with self._lock:
            self._stop_playback_requested = True

    def select_style(self, style_id: str) -> None:
        """Select a known style for the next transport start."""

        if style_id not in DEMO_STYLES:
            raise ValueError(f"unknown arranger style: {style_id}")
        self._raise_worker_error()
        with self._lock:
            self._style_requested = style_id

    @property
    def section(self) -> DemoSection:
        """Return the most recently rendered section."""

        return self._renderer.section

    @property
    def position_ticks(self) -> int:
        """Return the worker's rendered position, including pending restarts."""

        with self._lock:
            if self._start_requested or self._intro_requested:
                return 0
            renderer = self._renderer
        return renderer.position_ticks

    @property
    def style_id(self) -> str:
        """Return the style currently owned by the audio worker."""

        return self._style_id

    @property
    def error(self) -> str | None:
        """Return an asynchronous playback failure without raising it."""

        return str(self._error) if self._error is not None else None

    def close(self) -> None:
        """Stop the worker and close the PCM destination."""

        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._sink.close()
        renderer_close = getattr(self._renderer, "close", None)
        if callable(renderer_close):
            renderer_close()
        self._raise_worker_error()

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                with self._lock:
                    if self._style_requested is not None:
                        tempo = self._renderer.tempo_bpm
                        stopped = self._renderer.section is DemoSection.STOPPED
                        style_config = DemoAudioConfig(
                            tempo_bpm=tempo,
                            sample_rate=self._config.sample_rate,
                            chunk_frames=self._config.chunk_frames,
                        )
                        self._style_id = self._style_requested
                        previous_renderer = self._renderer
                        self._renderer = self._renderer_factory(
                            self._style_id, style_config
                        )
                        renderer_close = getattr(previous_renderer, "close", None)
                        if callable(renderer_close):
                            renderer_close()
                        if stopped:
                            self._renderer.stop()
                        self._style_requested = None
                    if self._reset_requested:
                        self._renderer.reset()
                        self._reset_requested = False
                    if self._tempo_requested is not None:
                        self._renderer.set_tempo(self._tempo_requested)
                        self._tempo_requested = None
                    if self._resume_requested:
                        self._renderer.resume_if_stopped()
                        self._resume_requested = False
                    if self._intro_requested:
                        self._renderer.start_intro()
                        self._intro_requested = False
                    if self._start_requested:
                        self._renderer.start_main()
                        self._start_requested = False
                    if self._ending_requested:
                        self._renderer.request_ending()
                        self._ending_requested = False
                    if self._stop_playback_requested:
                        self._renderer.stop()
                        self._stop_playback_requested = False
                    chord = self._chord
                pcm = self._renderer.render(self._config.chunk_frames, chord)
                self._sink.write(pcm)
        except (AudioPlaybackError, OSError) as error:
            self._error = AudioPlaybackError(str(error))
            self._stop.set()

    def _raise_worker_error(self) -> None:
        if self._error is not None:
            raise self._error


def run_audible_keyboard(
    *,
    keys: str | None,
    json_output: bool,
    tempo_bpm: int,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> int:
    """Run the keyboard chord source with the built-in audible arrangement."""

    if keys is not None:
        print(
            "ERROR: --play is interactive and cannot be combined with --keys",
            file=output_stream,
        )
        return 2
    config = DemoAudioConfig(tempo_bpm=tempo_bpm)
    try:
        sink = AplayPcmSink(config)
        arranger = RealtimeDemoArranger(config, sink)
        arranger.start()
        try:
            return run_keyboard(
                keys=None,
                json_output=json_output,
                input_stream=input_stream,
                output_stream=output_stream,
                event_handler=arranger.handle_event,
                playback_message=(f"Modern tango POC is playing at {tempo_bpm} BPM."),
                tempo_bpm=tempo_bpm,
            )
        finally:
            arranger.close()
    except (AudioPlaybackError, ValueError) as error:
        print(f"ERROR: {error}", file=output_stream)
        return 2
