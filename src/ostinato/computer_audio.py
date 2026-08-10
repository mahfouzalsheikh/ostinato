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


class AudioPlaybackError(RuntimeError):
    """Raised when the host PCM player cannot be started or stops unexpectedly."""


class PcmSink(Protocol):
    """Destination for signed 16-bit, little-endian, stereo PCM."""

    def write(self, pcm: bytes) -> None:
        """Write one contiguous audio buffer."""

    def close(self) -> None:
        """Release the destination."""


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


class DemoArrangementRenderer:
    """Render an original modern-tango loop without external samples."""

    STYLE_NAME: ClassVar[str] = "modern_tango"
    OUTPUT_MODE: ClassVar[str] = "procedural_pcm"
    MASTER_GAIN: ClassVar[float] = 2.6
    OUTPUT_LIMIT: ClassVar[int] = 30_000
    BEATS_PER_BAR: ClassVar[float] = 4.0
    SYNCOPATION_GROUPS: ClassVar[tuple[float, ...]] = (1.5, 1.5, 1.0)

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
            value = 0.0 if chord is None else self._render_frame(frame, chord)
            sample = round(math.tanh(value * self.MASTER_GAIN) * self.OUTPUT_LIMIT)
            samples.extend((sample, sample))
        self._frame_position += frame_count
        self._advance_section(self.beat_position)
        if sys.byteorder != "little":
            samples.byteswap()
        return samples.tobytes()

    def _render_frame(self, frame: int, chord: ChordState) -> float:
        beat = self._beat_at_frame(frame)
        section, section_beat = self._advance_section(beat)
        if section is DemoSection.STOPPED:
            return 0.0
        bar_phase = section_beat % self.BEATS_PER_BAR
        seconds_per_beat = 60 / self._tempo_bpm
        levels = self._ensemble_levels(section, section_beat)

        drums = self._render_drums(
            frame=frame,
            bar_phase=bar_phase,
            seconds_per_beat=seconds_per_beat,
        )
        percussion = self._render_auxiliary_percussion(
            frame=frame,
            pattern_beat=section_beat,
            bar_phase=bar_phase,
            seconds_per_beat=seconds_per_beat,
        )
        bass = self._render_bass(
            chord=chord,
            bar_phase=bar_phase,
            seconds_per_beat=seconds_per_beat,
        )
        piano = self._render_piano(
            chord=chord,
            bar_phase=bar_phase,
            seconds_per_beat=seconds_per_beat,
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
        )
        strings = self._render_strings(
            frame=frame,
            chord=chord,
            bar_phase=bar_phase,
            final_ending_bar=final_ending_bar,
        )

        mix = (
            levels.bass * bass
            + levels.piano * piano
            + levels.bandoneon * bandoneon
            + levels.drums * drums
            + levels.percussion * percussion
            + levels.strings * strings
        )
        fade_start = self._SECTION_LENGTH_BEATS - 0.5
        if section is DemoSection.ENDING and section_beat > fade_start:
            remaining = self._SECTION_LENGTH_BEATS - section_beat
            mix *= max(0.0, remaining / 0.5)
        return mix

    def _render_bass(
        self,
        *,
        chord: ChordState,
        bar_phase: float,
        seconds_per_beat: float,
    ) -> float:
        bass_pitch_class = (
            chord.bass_pitch_class
            if chord.bass_pitch_class is not None
            else chord.root_pitch_class
        )
        pulse, elapsed_beats = self._pulse_at(bar_phase, self._BASS_ONSETS)
        elapsed_seconds = elapsed_beats * seconds_per_beat
        note = 36 + bass_pitch_class + self._BASS_INTERVALS[pulse]
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
    ) -> float:
        pulse, elapsed_beats = self._pulse_at(bar_phase, self._BASS_ONSETS)
        elapsed_seconds = elapsed_beats * seconds_per_beat
        attack = min(1.0, elapsed_seconds * 110)
        envelope = attack * math.exp(-elapsed_seconds * 8.5)
        intervals = self._INTERVALS[chord.quality]
        selected = (
            intervals[pulse % len(intervals)],
            intervals[(pulse + 1) % len(intervals)] + 12,
        )
        piano = 0.0
        for interval in selected:
            frequency = self._midi_frequency(60 + chord.root_pitch_class + interval)
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
    ) -> float:
        onsets = self._FINAL_CHORD_ONSETS if final_ending_bar else self._CHORD_ONSETS
        _, elapsed_beats = self._pulse_at(bar_phase, onsets)
        elapsed_seconds = elapsed_beats * seconds_per_beat
        attack = min(1.0, elapsed_seconds * 100)
        final_accent = final_ending_bar and bar_phase >= 3.0
        decay = 3.0 if final_accent else 11
        envelope = attack * math.exp(-elapsed_seconds * decay)
        reed = 0.0
        intervals = self._INTERVALS[chord.quality]
        for interval in intervals:
            frequency = self._midi_frequency(60 + chord.root_pitch_class + interval)
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
            frequency = self._midi_frequency(67 + chord.root_pitch_class + interval)
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
    ) -> float:
        _, kick_elapsed_beats = self._pulse_at(bar_phase, self._BASS_ONSETS)
        kick_seconds = kick_elapsed_beats * seconds_per_beat
        kick_envelope = math.exp(-kick_seconds * 15)
        kick_cycles = (47 * kick_seconds) + (
            (70 / 30) * (1 - math.exp(-30 * kick_seconds))
        )
        kick = 0.25 * kick_envelope * math.sin(math.tau * kick_cycles)

        _, snare_elapsed_beats = self._pulse_at(bar_phase, self._CHORD_ONSETS)
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
    ) -> float:
        click_onsets = (0.75, 2.25, 3.75)
        _, click_elapsed_beats = self._pulse_at(bar_phase, click_onsets)
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
        shaker_accent = 1.5 if sixteenth % 16 in (0, 6, 12) else 0.65
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


class AplayPcmSink:
    """Stream PCM to the host's default ALSA/PipeWire route through ``aplay``."""

    def __init__(self, config: DemoAudioConfig) -> None:
        executable = shutil.which("aplay")
        if executable is None:
            raise AudioPlaybackError(
                "aplay is not available; install ALSA utilities or run without --play"
            )
        command = [
            executable,
            "--quiet",
            "--file-type=raw",
            "--format=S16_LE",
            "--channels=2",
            f"--rate={config.sample_rate}",
            "--period-time=10000",
            "--buffer-time=40000",
        ]
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
        try:
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=1)

    def _failure_detail(self) -> str:
        stderr = self._process.stderr
        detail = stderr.read().decode(errors="replace").strip() if stderr else ""
        return f"aplay stopped unexpectedly{f': {detail}' if detail else ''}"


class RealtimeDemoArranger:
    """Own the audio worker and apply explicit keyboard events to its chord state."""

    def __init__(
        self,
        config: DemoAudioConfig,
        sink: PcmSink,
        *,
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
    ) -> None:
        self._config = config
        self._sink = sink
        self._renderer = DemoArrangementRenderer(config)
        self._thread_factory = thread_factory
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._chord: ChordState | None = None
        self._reset_requested = False
        self._tempo_requested: int | None = None
        self._resume_requested = False
        self._intro_requested = False
        self._ending_requested = False
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

    def close(self) -> None:
        """Stop the worker and close the PCM destination."""

        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._sink.close()
        self._raise_worker_error()

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                with self._lock:
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
                    if self._ending_requested:
                        self._renderer.request_ending()
                        self._ending_requested = False
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
