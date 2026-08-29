"""Native FluidSynth renderer for sampled arranger accompaniment.

The module has no import-time dependency on FluidSynth. The shared procedural
renderer remains available for CI and hosts without a configured SoundFont.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import heapq
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Protocol

from ostinato.computer_audio import (
    BASS_C_NOTE,
    DEMO_STYLES,
    LOW_C_NOTE,
    MIDDLE_C_NOTE,
    UPPER_C_NOTE,
    DemoAudioConfig,
    DemoSection,
    EnsembleLevels,
    GrooveBar,
)
from ostinato.domain import ChordQuality, ChordState
from ostinato.keyboard_input import MAX_TEMPO_BPM, MIN_TEMPO_BPM

MELODIC_CHANNELS = (0, 1, 2, 3)
DRUM_CHANNEL = 9
KICK_NOTE = 36
SIDE_STICK_NOTE = 37
SNARE_NOTE = 38
CLOSED_HIHAT_NOTE = 42
TAMBOURINE_NOTE = 54
RIDE_CYMBAL_NOTE = 51
MARACAS_NOTE = 70
CLAVES_NOTE = 75
SOUNDFONT_GAIN = 1.0


class SoundFontError(RuntimeError):
    """A configured SoundFont or native FluidSynth operation failed."""


class SynthEngine(Protocol):
    """Small native-synth boundary used by deterministic renderer tests."""

    def program_select(self, channel: int, bank: int, program: int) -> None: ...

    def control_change(self, channel: int, controller: int, value: int) -> None: ...

    def set_gain(self, gain: float) -> None: ...

    def note_on(self, channel: int, note: int, velocity: int) -> None: ...

    def note_off(self, channel: int, note: int) -> None: ...

    def render(self, frame_count: int) -> bytes: ...

    def close(self) -> None: ...


class FluidSynthEngine:
    """Render one SoundFont through libfluidsynth into interleaved stereo PCM."""

    def __init__(self, config: DemoAudioConfig, soundfont_path: str) -> None:
        path = Path(soundfont_path)
        if not path.is_file():
            raise SoundFontError(f"configured SoundFont does not exist: {path}")
        library_name = ctypes.util.find_library("fluidsynth")
        if library_name is None:
            raise SoundFontError("libfluidsynth is not available")
        self._library = ctypes.CDLL(library_name)
        self._bind_library()
        self._settings = self._library.new_fluid_settings()
        if not self._settings:
            raise SoundFontError("FluidSynth could not allocate settings")
        self._synth: int | None = None
        self._set_num("synth.sample-rate", config.sample_rate)
        # Start from a neutral native level. Each sampled palette applies its
        # measured style gain after loading so sparse bossa and dense orchestral
        # sections can reach comparable loudness without clipping.
        self._set_num("synth.gain", SOUNDFONT_GAIN)
        self._set_int("synth.polyphony", 128)
        self._set_int("synth.reverb.active", 1)
        self._set_int("synth.chorus.active", 1)
        synth = self._library.new_fluid_synth(self._settings)
        if not synth:
            self._library.delete_fluid_settings(self._settings)
            raise SoundFontError("FluidSynth could not allocate a synthesizer")
        self._synth = synth
        self._soundfont_id = self._library.fluid_synth_sfload(
            synth, str(path).encode(), 1
        )
        if self._soundfont_id < 0:
            self.close()
            raise SoundFontError(f"FluidSynth could not load SoundFont: {path}")

    def program_select(self, channel: int, bank: int, program: int) -> None:
        self._call(
            "fluid_synth_program_select",
            channel,
            self._soundfont_id,
            bank,
            program,
        )

    def control_change(self, channel: int, controller: int, value: int) -> None:
        self._call("fluid_synth_cc", channel, controller, value)

    def set_gain(self, gain: float) -> None:
        self._library.fluid_synth_set_gain(self._require_synth(), gain)

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self._call("fluid_synth_noteon", channel, note, velocity)

    def note_off(self, channel: int, note: int) -> None:
        synth = self._require_synth()
        # FluidSynth reports FLUID_FAILED when a voice has already completed.
        # That is a valid MIDI lifecycle outcome (especially for short drum
        # samples and overlapping repeated notes), not an audio-engine failure.
        self._library.fluid_synth_noteoff(synth, channel, note)

    def render(self, frame_count: int) -> bytes:
        if frame_count < 0:
            raise ValueError("frame_count cannot be negative")
        if frame_count == 0:
            return b""
        synth = self._require_synth()
        buffer = (ctypes.c_int16 * (frame_count * 2))()
        result = self._library.fluid_synth_write_s16(
            synth,
            frame_count,
            buffer,
            0,
            2,
            buffer,
            1,
            2,
        )
        if result != 0:
            raise SoundFontError("FluidSynth failed while rendering PCM")
        return bytes(buffer)

    def close(self) -> None:
        synth = self._synth
        if synth is not None:
            self._library.delete_fluid_synth(synth)
            self._synth = None
        settings = getattr(self, "_settings", None)
        if settings:
            self._library.delete_fluid_settings(settings)
            self._settings = None

    def _bind_library(self) -> None:
        library = self._library
        library.new_fluid_settings.restype = ctypes.c_void_p
        library.delete_fluid_settings.argtypes = [ctypes.c_void_p]
        library.fluid_settings_setnum.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_double,
        ]
        library.fluid_settings_setint.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        library.new_fluid_synth.argtypes = [ctypes.c_void_p]
        library.new_fluid_synth.restype = ctypes.c_void_p
        library.delete_fluid_synth.argtypes = [ctypes.c_void_p]
        library.fluid_synth_sfload.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        library.fluid_synth_sfload.restype = ctypes.c_int
        for name in (
            "fluid_synth_program_select",
            "fluid_synth_cc",
            "fluid_synth_noteon",
            "fluid_synth_noteoff",
        ):
            getattr(library, name).restype = ctypes.c_int
        library.fluid_synth_program_select.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        for name in ("fluid_synth_cc", "fluid_synth_noteon"):
            getattr(library, name).argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
            ]
        library.fluid_synth_noteoff.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
        ]
        library.fluid_synth_write_s16.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
        ]
        library.fluid_synth_write_s16.restype = ctypes.c_int
        library.fluid_synth_set_gain.argtypes = [ctypes.c_void_p, ctypes.c_float]
        library.fluid_synth_set_gain.restype = None

    def _set_num(self, name: str, value: float) -> None:
        if (
            self._library.fluid_settings_setnum(
                self._settings, name.encode(), float(value)
            )
            < 0
        ):
            raise SoundFontError(f"FluidSynth rejected setting {name}")

    def _set_int(self, name: str, value: int) -> None:
        if (
            self._library.fluid_settings_setint(self._settings, name.encode(), value)
            < 0
        ):
            raise SoundFontError(f"FluidSynth rejected setting {name}")

    def _call(self, name: str, *values: int) -> None:
        synth = self._require_synth()
        if getattr(self._library, name)(synth, *values) != 0:
            raise SoundFontError(f"FluidSynth call failed: {name}")

    def _require_synth(self) -> int:
        if self._synth is None:
            raise SoundFontError("FluidSynth engine is closed")
        return self._synth


@dataclass(frozen=True, slots=True)
class SoundFontPalette:
    """General MIDI programs and percussion color for one style."""

    bass_program: int
    comp_program: int
    reed_program: int
    pad_program: int
    auxiliary_note: int
    snare_note: int = SNARE_NOTE
    timekeeper_note: int = CLOSED_HIHAT_NOTE
    gain: float = 1.0
    reed_high_note: int | None = None


PALETTES: dict[str, SoundFontPalette] = {
    # TimGM6mb programs 21 and 23 use sharply flat sample zones above C5.
    # Muted trumpet is stable through C7 and suits tango accents; fold only
    # its extreme generated voicings back into that measured range. English
    # horn supplies the waltz's sustained color without the faulty zones.
    "modern_tango": SoundFontPalette(
        32, 0, 59, 48, CLAVES_NOTE, gain=1.25, reed_high_note=96
    ),
    "classic_tango": SoundFontPalette(
        32, 0, 59, 48, CLAVES_NOTE, gain=1.25, reed_high_note=96
    ),
    "classic_waltz": SoundFontPalette(32, 0, 69, 48, RIDE_CYMBAL_NOTE, gain=1.05),
    "bossa_nova": SoundFontPalette(
        33, 24, 11, 48, MARACAS_NOTE, SIDE_STICK_NOTE, CLOSED_HIHAT_NOTE, 1.9
    ),
    "swing_foxtrot": SoundFontPalette(
        32, 0, 65, 48, SIDE_STICK_NOTE, SNARE_NOTE, RIDE_CYMBAL_NOTE, 1.85
    ),
    "alpine_polka": SoundFontPalette(32, 21, 56, 48, TAMBOURINE_NOTE, gain=1.8),
}


@dataclass(order=True, slots=True)
class _SynthEvent:
    frame: int
    order: int
    channel: int = field(compare=False)
    note: int = field(compare=False)
    velocity: int = field(compare=False)
    duration_frames: int = field(compare=False, default=0)


class SoundFontArrangementRenderer:
    """Render style grooves with sampled GM instruments through FluidSynth."""

    _INTERVALS: ClassVar[dict[ChordQuality, tuple[int, ...]]] = {
        ChordQuality.MAJOR: (0, 4, 7),
        ChordQuality.MINOR: (0, 3, 7),
        ChordQuality.DOMINANT_SEVENTH: (0, 4, 7, 10),
        ChordQuality.DIMINISHED: (0, 3, 6),
    }

    def __init__(
        self,
        style_id: str,
        config: DemoAudioConfig,
        soundfont_path: str,
        *,
        engine_factory: Callable[
            [DemoAudioConfig, str], SynthEngine
        ] = FluidSynthEngine,
    ) -> None:
        if style_id not in DEMO_STYLES:
            raise ValueError(f"unknown arranger style: {style_id}")
        if style_id not in PALETTES:
            raise ValueError(f"style has no SoundFont palette: {style_id}")
        self._definition = DEMO_STYLES[style_id]
        self._renderer_type = self._definition.renderer
        self._config = config
        self._engine = engine_factory(config, soundfont_path)
        self._tempo_bpm = config.tempo_bpm
        self._frame_position = 0
        self._tempo_epoch_frame = 0
        self._tempo_epoch_beat = 0.0
        self._section = DemoSection.MAIN
        self._section_start_beat = 0.0
        self._ending_at_beat: float | None = None
        self._events: list[_SynthEvent] = []
        self._event_order = 0
        self._chord_signature: tuple[int, ChordQuality, int | None] | None = None
        self._silent = True
        self._closed = False
        self._configure_palette(PALETTES[style_id])

    @property
    def tempo_bpm(self) -> int:
        return self._tempo_bpm

    @property
    def section(self) -> DemoSection:
        self._advance_section(self._beat_at_frame(self._frame_position))
        return self._section

    def set_tempo(self, tempo_bpm: int) -> None:
        if not MIN_TEMPO_BPM <= tempo_bpm <= MAX_TEMPO_BPM:
            raise ValueError(
                f"tempo_bpm must be between {MIN_TEMPO_BPM} and {MAX_TEMPO_BPM}"
            )
        beat = self._beat_at_frame(self._frame_position)
        self._tempo_epoch_frame = self._frame_position
        self._tempo_epoch_beat = beat
        self._tempo_bpm = tempo_bpm

    def reset(self) -> None:
        self._all_sound_off()
        self._frame_position = 0
        self._tempo_epoch_frame = 0
        self._tempo_epoch_beat = 0.0
        self._section = DemoSection.MAIN
        self._section_start_beat = 0.0
        self._ending_at_beat = None
        self._chord_signature = None

    def start_main(self) -> None:
        self.reset()

    def stop(self) -> None:
        self._all_sound_off()
        self._section = DemoSection.STOPPED
        self._ending_at_beat = None

    def start_intro(self) -> None:
        self.reset()
        self._section = DemoSection.INTRO

    def request_ending(self) -> None:
        if self._section is DemoSection.STOPPED:
            return
        beat = self._beat_at_frame(self._frame_position)
        beats_per_bar = self._renderer_type.BEATS_PER_BAR
        self._ending_at_beat = (math.floor(beat / beats_per_bar) + 1) * beats_per_bar

    def resume_if_stopped(self) -> None:
        if self.section is DemoSection.STOPPED:
            self.reset()

    def render(self, frame_count: int, chord: ChordState | None) -> bytes:
        if frame_count < 0:
            raise ValueError("frame_count cannot be negative")
        if frame_count == 0:
            return b""
        start_frame = self._frame_position
        end_frame = start_frame + frame_count
        self._advance_section(self._beat_at_frame(start_frame))
        if self._section is DemoSection.STOPPED or chord is None:
            if not self._silent:
                self._all_sound_off()
            self._frame_position = end_frame
            self._advance_section(self._beat_at_frame(end_frame))
            return bytes(frame_count * 4)

        signature = (chord.root_pitch_class, chord.quality, chord.bass_pitch_class)
        if signature != self._chord_signature:
            self._change_harmony(chord, start_frame)
            self._chord_signature = signature
        self._silent = False
        pcm = self._render_active_span(start_frame, end_frame, chord)
        self._frame_position = end_frame
        self._advance_section(self._beat_at_frame(end_frame))
        return pcm

    def close(self) -> None:
        if self._closed:
            return
        self._all_sound_off()
        self._engine.close()
        self._closed = True

    def _render_active_span(
        self, start_frame: int, end_frame: int, chord: ChordState
    ) -> bytes:
        start_beat = self._beat_at_frame(start_frame)
        end_beat = self._beat_at_frame(end_frame)
        self._queue_style_events(start_beat, end_beat, chord)
        chunks: list[bytes] = []
        cursor = start_frame
        while self._events and self._events[0].frame < end_frame:
            event_frame = max(cursor, self._events[0].frame)
            if event_frame > cursor:
                chunks.append(self._engine.render(event_frame - cursor))
                cursor = event_frame
            while self._events and self._events[0].frame <= cursor:
                event = heapq.heappop(self._events)
                if event.velocity == 0:
                    self._engine.note_off(event.channel, event.note)
                else:
                    self._engine.note_on(event.channel, event.note, event.velocity)
                    self._queue_note_off(event)
        if cursor < end_frame:
            chunks.append(self._engine.render(end_frame - cursor))
        return b"".join(chunks)

    def _queue_style_events(
        self, start_beat: float, end_beat: float, chord: ChordState
    ) -> None:
        section, section_beat = self._advance_section(start_beat)
        if section is DemoSection.STOPPED:
            return
        beats_per_bar = self._renderer_type.BEATS_PER_BAR
        first_bar = math.floor(section_beat / beats_per_bar)
        last_bar = math.floor(
            max(section_beat, section_beat + (end_beat - start_beat) - 1e-9)
            / beats_per_bar
        )
        for bar_index in range(first_bar, last_bar + 1):
            groove = self._renderer_type._GROOVE[
                bar_index % len(self._renderer_type._GROOVE)
            ]
            bar_section_beat = bar_index * beats_per_bar
            bar_absolute_beat = self._section_start_beat + bar_section_beat
            levels = self._renderer_type._ensemble_levels(section, bar_section_beat)
            phrase_dynamic = self._renderer_type._PHRASE_DYNAMICS[
                bar_index % len(self._renderer_type._PHRASE_DYNAMICS)
            ]
            final_bar = (
                section is DemoSection.ENDING
                and bar_section_beat
                >= self._renderer_type._SECTION_LENGTH_BEATS - beats_per_bar
            )
            self._queue_groove_bar(
                bar_absolute_beat,
                start_beat,
                end_beat,
                chord,
                groove,
                levels,
                phrase_dynamic,
                final_bar,
            )

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
        palette = PALETTES[self._definition.id]
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
                0,
                BASS_C_NOTE + bass_root + interval,
                self._velocity(
                    94,
                    levels.bass,
                    dynamic * self._accent(groove.bass_accents, pulse),
                ),
                self._renderer_type._BASS_DURATION_BEATS,
            )

        chord_onsets = (
            self._renderer_type._FINAL_CHORD_ONSETS
            if final_bar
            else groove.chord_onsets
        )
        intervals = self._INTERVALS[chord.quality]
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
                else self._renderer_type._CHORD_DURATION_BEATS
            )
            for interval in voicing:
                self._queue_at_beat(
                    bar_beat + onset,
                    start_beat,
                    end_beat,
                    1,
                    MIDDLE_C_NOTE + chord.root_pitch_class + interval,
                    self._velocity(
                        78,
                        levels.piano,
                        dynamic * self._accent(groove.chord_accents, pulse),
                    ),
                    duration,
                )

        reed_onsets = (
            chord_onsets
            if final_bar
            else (
                groove.reed_onsets
                if groove.reed_onsets is not None
                else groove.chord_onsets
            )
        )
        for pulse, onset in enumerate(reed_onsets):
            rotation = pulse + groove.voicing_rotation
            reed_voicing = tuple(
                intervals[(rotation + voice) % len(intervals)]
                + (12 if rotation + voice >= len(intervals) else 0)
                for voice in range(min(3, len(intervals)))
            )
            duration = (
                self._renderer_type.BEATS_PER_BAR - onset - 0.05
                if final_bar and pulse == len(reed_onsets) - 1
                else self._renderer_type._REED_DURATION_BEATS
            )
            for interval in reed_voicing:
                reed_note = UPPER_C_NOTE + chord.root_pitch_class + interval
                if palette.reed_high_note is not None:
                    while reed_note > palette.reed_high_note:
                        reed_note -= 12
                self._queue_at_beat(
                    bar_beat + onset,
                    start_beat,
                    end_beat,
                    2,
                    reed_note,
                    self._velocity(
                        66,
                        levels.bandoneon,
                        dynamic * self._accent(groove.reed_accents, pulse),
                    ),
                    duration,
                )

        pad_onsets = groove.pad_onsets if groove.pad_onsets is not None else (0.0,)
        for onset in pad_onsets:
            pad_note_duration = self._renderer_type._PAD_DURATION_BEATS
            if pad_note_duration is None:
                pad_note_duration = self._renderer_type.BEATS_PER_BAR - onset - 0.05
            for interval in intervals[:3]:
                self._queue_at_beat(
                    bar_beat + onset,
                    start_beat,
                    end_beat,
                    3,
                    LOW_C_NOTE + chord.root_pitch_class + interval,
                    self._velocity(58, levels.strings, dynamic),
                    pad_note_duration,
                )

        for onset in groove.kick_onsets:
            self._queue_drum(
                bar_beat + onset,
                start_beat,
                end_beat,
                KICK_NOTE,
                self._velocity(98, levels.drums, dynamic),
            )
        for onset in groove.snare_onsets:
            self._queue_drum(
                bar_beat + onset,
                start_beat,
                end_beat,
                palette.snare_note,
                self._velocity(84, levels.drums, dynamic),
            )
        for onset in groove.auxiliary_onsets:
            self._queue_drum(
                bar_beat + onset,
                start_beat,
                end_beat,
                palette.auxiliary_note,
                self._velocity(68, levels.percussion, dynamic),
            )
        hat_onsets = (
            groove.hat_onsets
            if groove.hat_onsets is not None
            else tuple(
                step * 0.5
                for step in range(round(self._renderer_type.BEATS_PER_BAR / 0.5))
            )
        )
        for step, onset in enumerate(hat_onsets):
            self._queue_drum(
                bar_beat + onset,
                start_beat,
                end_beat,
                palette.timekeeper_note,
                self._velocity(
                    58,
                    levels.percussion,
                    dynamic * self._accent(groove.hat_accents, step),
                ),
            )

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
        frame = self._frame_at_beat(beat)
        duration_frames = max(
            1,
            round(duration_beats * 60 * self._config.sample_rate / self._tempo_bpm),
        )
        self._event_order += 1
        heapq.heappush(
            self._events,
            _SynthEvent(
                frame,
                self._event_order,
                channel,
                max(0, min(127, note)),
                velocity,
                duration_frames,
            ),
        )

    def _queue_drum(
        self,
        beat: float,
        start_beat: float,
        end_beat: float,
        note: int,
        velocity: int,
    ) -> None:
        self._queue_at_beat(
            beat,
            start_beat,
            end_beat,
            DRUM_CHANNEL,
            note,
            velocity,
            0.10,
        )

    def _queue_note_off(self, event: _SynthEvent) -> None:
        self._event_order += 1
        heapq.heappush(
            self._events,
            _SynthEvent(
                event.frame + event.duration_frames,
                self._event_order,
                event.channel,
                event.note,
                0,
            ),
        )

    def _change_harmony(self, chord: ChordState, frame: int) -> None:
        for channel in MELODIC_CHANNELS:
            # CC123 releases notes through the preset's envelope.  That is too
            # slow for live harmony changes: TimGM6mb's string preset can keep
            # the previous chord clearly audible for more than a second.  Cut
            # the stale voices first, then clear the channel's note state.
            self._engine.control_change(channel, 120, 0)
            self._engine.control_change(channel, 123, 0)
        self._events = [
            event for event in self._events if event.channel == DRUM_CHANNEL
        ]
        heapq.heapify(self._events)
        intervals = self._INTERVALS[chord.quality]
        immediate_voices = [(1, MIDDLE_C_NOTE, 52, 0.22)]
        if any(groove.pad_onsets != () for groove in self._renderer_type._GROOVE):
            pad_duration = self._renderer_type._PAD_DURATION_BEATS
            immediate_voices.append(
                (
                    3,
                    LOW_C_NOTE,
                    42,
                    pad_duration
                    if pad_duration is not None
                    else self._renderer_type.BEATS_PER_BAR,
                )
            )
        for channel, base, velocity, duration in immediate_voices:
            for interval in intervals:
                self._event_order += 1
                event = _SynthEvent(
                    frame,
                    self._event_order,
                    channel,
                    base + chord.root_pitch_class + interval,
                    velocity,
                    max(
                        1,
                        round(
                            duration * 60 * self._config.sample_rate / self._tempo_bpm
                        ),
                    ),
                )
                heapq.heappush(self._events, event)

    def _configure_palette(self, palette: SoundFontPalette) -> None:
        self._engine.set_gain(palette.gain)
        for channel, program in enumerate(
            (
                palette.bass_program,
                palette.comp_program,
                palette.reed_program,
                palette.pad_program,
            )
        ):
            self._engine.program_select(channel, 0, program)
        self._engine.program_select(DRUM_CHANNEL, 128, 0)
        for channel, pan, volume in (
            (0, 58, 104),
            (1, 40, 96),
            (2, 82, 92),
            (3, 48, 78),
            (DRUM_CHANNEL, 64, 102),
        ):
            self._engine.control_change(channel, 10, pan)
            self._engine.control_change(channel, 7, volume)

    def _all_sound_off(self) -> None:
        for channel in (*MELODIC_CHANNELS, DRUM_CHANNEL):
            self._engine.control_change(channel, 120, 0)
            self._engine.control_change(channel, 123, 0)
        self._events.clear()
        self._silent = True

    @staticmethod
    def _velocity(base: int, level: float, dynamic: float) -> int:
        return max(0, min(127, round(base * level * dynamic)))

    @staticmethod
    def _accent(accents: tuple[float, ...], index: int) -> float:
        return accents[index] if index < len(accents) else 1.0

    def _advance_section(self, beat: float) -> tuple[DemoSection, float]:
        if (
            self._ending_at_beat is not None
            and beat >= self._ending_at_beat
            and self._section is not DemoSection.STOPPED
        ):
            self._all_sound_off()
            self._section = DemoSection.ENDING
            self._section_start_beat = self._ending_at_beat
            self._ending_at_beat = None
        section_beat = beat - self._section_start_beat
        length = self._renderer_type._SECTION_LENGTH_BEATS
        if self._section is DemoSection.INTRO and section_beat >= length:
            self._section = DemoSection.MAIN
            self._section_start_beat += length
            section_beat = beat - self._section_start_beat
        elif self._section is DemoSection.ENDING and section_beat >= length:
            self._all_sound_off()
            self._section = DemoSection.STOPPED
            section_beat = length
        return self._section, section_beat

    def _beat_at_frame(self, frame: int) -> float:
        elapsed_frames = frame - self._tempo_epoch_frame
        return self._tempo_epoch_beat + (
            elapsed_frames * self._tempo_bpm / (self._config.sample_rate * 60)
        )

    def _frame_at_beat(self, beat: float) -> int:
        elapsed_beats = beat - self._tempo_epoch_beat
        return self._tempo_epoch_frame + round(
            elapsed_beats * self._config.sample_rate * 60 / self._tempo_bpm
        )
