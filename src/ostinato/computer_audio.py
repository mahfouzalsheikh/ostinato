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


class DemoArrangementRenderer:
    """Render an original drums, bass, and chord loop without external samples."""

    _INTERVALS: ClassVar[dict[ChordQuality, tuple[int, ...]]] = {
        ChordQuality.MAJOR: (0, 4, 7),
        ChordQuality.MINOR: (0, 3, 7),
        ChordQuality.DOMINANT_SEVENTH: (0, 4, 7, 10),
        ChordQuality.DIMINISHED: (0, 3, 6),
    }

    def __init__(self, config: DemoAudioConfig) -> None:
        self._config = config
        self._frame_position = 0
        self._tempo_bpm = config.tempo_bpm
        self._tempo_epoch_frame = 0
        self._tempo_epoch_beat = 0.0

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
        """Return the demonstration transport to the start of its bar."""

        self._frame_position = 0
        self._tempo_epoch_frame = 0
        self._tempo_epoch_beat = 0.0

    def render(self, frame_count: int, chord: ChordState | None) -> bytes:
        """Render a buffer and advance by exactly ``frame_count`` samples."""

        if frame_count < 0:
            raise ValueError("frame_count cannot be negative")
        samples = array("h")
        for frame in range(self._frame_position, self._frame_position + frame_count):
            value = 0.0 if chord is None else self._render_frame(frame, chord)
            sample = round(max(-1.0, min(1.0, value)) * 24_000)
            samples.extend((sample, sample))
        self._frame_position += frame_count
        if sys.byteorder != "little":
            samples.byteswap()
        return samples.tobytes()

    def _render_frame(self, frame: int, chord: ChordState) -> float:
        sample_rate = self._config.sample_rate
        time_seconds = frame / sample_rate
        beat = self._beat_at_frame(frame)
        quarter = math.floor(beat)
        quarter_phase = beat - quarter
        eighth = math.floor(beat * 2)
        eighth_phase = (beat * 2) - eighth

        seconds_per_beat = 60 / self._tempo_bpm
        quarter_seconds = quarter_phase * seconds_per_beat
        eighth_seconds = eighth_phase * seconds_per_beat / 2

        kick = 0.0
        if quarter % 4 in (0, 2):
            kick_envelope = math.exp(-quarter_seconds * 13)
            kick_cycles = (48 * quarter_seconds) + (
                (82 / 28) * (1 - math.exp(-28 * quarter_seconds))
            )
            kick = 0.42 * kick_envelope * math.sin(math.tau * kick_cycles)

        noise = self._noise(frame)
        snare = 0.0
        if quarter % 4 in (1, 3):
            snare_envelope = math.exp(-quarter_seconds * 18)
            snare_body = math.sin(math.tau * 185 * quarter_seconds)
            snare = snare_envelope * ((0.11 * snare_body) + (0.09 * noise))

        hat_envelope = math.exp(-eighth_seconds * 55)
        hat_metal = (
            sum(
                math.sin(math.tau * frequency * eighth_seconds)
                for frequency in (5_400, 7_100, 8_300)
            )
            / 3
        )
        hi_hat = 0.035 * hat_envelope * hat_metal

        bass_pitch_class = (
            chord.bass_pitch_class
            if chord.bass_pitch_class is not None
            else chord.root_pitch_class
        )
        if quarter % 2:
            bass_pitch_class = (bass_pitch_class + 7) % 12
        bass_note = 36 + bass_pitch_class
        bass_frequency = self._midi_frequency(bass_note)
        bass_attack = min(1.0, quarter_phase * 35)
        bass_envelope = bass_attack * math.exp(-quarter_phase * 2.4)
        bass = 0.22 * bass_envelope * math.sin(math.tau * bass_frequency * time_seconds)

        chord_stab = 0.0
        if eighth % 2:
            stab_envelope = min(1.0, eighth_phase * 28) * math.exp(-eighth_phase * 3.2)
            intervals = self._INTERVALS[chord.quality]
            for interval in intervals:
                note = 60 + chord.root_pitch_class + interval
                chord_stab += math.sin(
                    math.tau * self._midi_frequency(note) * time_seconds
                )
            chord_stab *= 0.15 * stab_envelope / len(intervals)

        return kick + snare + hi_hat + bass + chord_stab

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
    def _noise(frame: int) -> float:
        # A deterministic integer hash keeps offline/test renders reproducible.
        value = frame & 0xFFFFFFFF
        value ^= value >> 16
        value = (value * 0x7FEB352D) & 0xFFFFFFFF
        value ^= value >> 15
        value = (value * 0x846CA68B) & 0xFFFFFFFF
        value ^= value >> 16
        return (value / 2_147_483_647.5) - 1.0


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
            elif event.kind is KeyboardEventKind.CLEAR:
                self._chord = None
            elif event.kind is KeyboardEventKind.PANIC:
                self._chord = None
                self._reset_requested = True
            elif event.kind is KeyboardEventKind.TEMPO:
                self._tempo_requested = event.tempo_bpm

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
                playback_message=(
                    "Built-in drums, bass, and chord audio is playing at "
                    f"{tempo_bpm} BPM."
                ),
                tempo_bpm=tempo_bpm,
            )
        finally:
            arranger.close()
    except (AudioPlaybackError, ValueError) as error:
        print(f"ERROR: {error}", file=output_stream)
        return 2
