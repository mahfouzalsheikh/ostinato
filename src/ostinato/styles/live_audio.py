"""Live SoundFont playback for validated, locally imported arranger styles."""

from __future__ import annotations

import heapq
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Protocol

from ostinato.computer_audio import (
    TRANSPORT_TICKS_PER_BEAT,
    DemoAudioConfig,
    DemoSection,
)
from ostinato.domain import ChordQuality, ChordState
from ostinato.keyboard_input import MAX_TEMPO_BPM, MIN_TEMPO_BPM
from ostinato.soundfont_audio import FluidSynthEngine
from ostinato.styles.models import (
    ChordVariation,
    ControlChangeEvent,
    NoteEvent,
    PitchBendEvent,
    ProgramChangeEvent,
    Style,
    StyleElementType,
    StyleTrackRole,
)

PERCUSSION_ROLES = {StyleTrackRole.DRUM, StyleTrackRole.PERCUSSION}
REQUIRED_SECTIONS = {
    "main": StyleElementType.VARIATION_1,
    "intro": StyleElementType.INTRO_1,
    "fill_1": StyleElementType.FILL_1,
    "fill_2": StyleElementType.FILL_2,
    "ending": StyleElementType.ENDING_1,
}


class ImportedStyleSynth(Protocol):
    def program_select(self, channel: int, bank: int, program: int) -> None: ...
    def control_change(self, channel: int, controller: int, value: int) -> None: ...
    def pitch_bend(self, channel: int, value: int) -> None: ...
    def set_gain(self, gain: float) -> None: ...
    def note_on(self, channel: int, note: int, velocity: int) -> None: ...
    def note_off(self, channel: int, note: int) -> None: ...
    def render(self, frame_count: int) -> bytes: ...
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ImportedStylePlaybackInfo:
    """The explicit live subset and inferred tonal anchor for one import."""

    sections: dict[str, ChordVariation]
    beats_per_bar: int
    anchor_pitch_class: int


@dataclass(frozen=True, slots=True)
class _Action:
    tick: int
    order: int
    channel: int
    role: StyleTrackRole
    kind: str
    first: int
    second: int = 0


@dataclass(order=True, slots=True)
class _QueuedAction:
    frame: int
    order: int
    action: _Action = field(compare=False)


def imported_style_playback_info(style: Style) -> ImportedStylePlaybackInfo:
    """Validate the deliberately bounded CV1 live-playback policy."""

    if style.version != 1:
        raise ValueError("only version-1 imported styles are supported")
    if style.time_signature is None or style.time_signature[1] != 4:
        raise ValueError("live imported styles require an x/4 time signature")
    beats_per_bar = style.time_signature[0]
    if not 2 <= beats_per_bar <= 4:
        raise ValueError("live imported styles require 2, 3, or 4 beats per bar")
    sections: dict[str, ChordVariation] = {}
    for name, element_type in REQUIRED_SECTIONS.items():
        section = next(
            (item for item in style.elements if item.type is element_type), None
        )
        variation = (
            next((item for item in section.chord_variations if item.number == 1), None)
            if section is not None
            else None
        )
        if variation is None:
            raise ValueError(f"imported style has no {element_type.value} CV1")
        sections[name] = variation
    bass_notes = sorted(
        (
            event
            for track in sections["main"].tracks
            if track.role is StyleTrackRole.BASS
            for event in track.events
            if isinstance(event, NoteEvent)
        ),
        key=lambda event: (event.start_tick, event.note),
    )
    anchor_notes = bass_notes
    if not anchor_notes:
        anchor_notes = sorted(
            (
                event
                for track in sections["main"].tracks
                if track.role not in PERCUSSION_ROLES
                for event in track.events
                if isinstance(event, NoteEvent)
            ),
            key=lambda event: (event.start_tick, event.note),
        )
    if not anchor_notes:
        raise ValueError("Variation 1 CV1 has no melodic note for a tonal anchor")
    return ImportedStylePlaybackInfo(sections, beats_per_bar, anchor_notes[0].note % 12)


def imported_style_rhythm_spans(style: Style) -> tuple[float, ...]:
    """Derive live-tempo candidate gaps from CV1 bass and accompaniment attacks."""

    info = imported_style_playback_info(style)
    variation = info.sections["main"]
    positions = sorted(
        {
            event.start_tick / style.ticks_per_beat
            for track in variation.tracks
            if track.role not in PERCUSSION_ROLES
            for event in track.events
            if isinstance(event, NoteEvent)
        }
    )
    length_beats = variation.length_ticks / style.ticks_per_beat
    gaps = {
        round(later - earlier, 3)
        for earlier, later in pairwise(positions)
        if later - earlier >= 0.25
    }
    if positions:
        wrap = length_beats - positions[-1] + positions[0]
        if wrap >= 0.25:
            gaps.add(round(wrap, 3))
    gaps.update((1.0, 2.0, float(info.beats_per_bar)))
    return tuple(sorted(gaps))


class ImportedStyleArrangementRenderer:
    """Schedule CV1 source events while applying Ostinato chord adaptation.

    KORG's SMF export does not carry NTT/key parameters. Melodic source notes
    are therefore root-transposed from the first main bass note. When CV1 has
    no bass notes, the lowest melodic note at its earliest onset is the local
    fallback anchor. Source thirds, fifths, and sevenths are adapted to
    Ostinato's detected chord quality. Drum and percussion note numbers are
    always preserved.
    """

    def __init__(
        self,
        style: Style,
        config: DemoAudioConfig,
        soundfont_path: str,
        *,
        engine_factory: Callable[
            [DemoAudioConfig, str], ImportedStyleSynth
        ] = FluidSynthEngine,
    ) -> None:
        self._style = style
        self._info = imported_style_playback_info(style)
        self._config = config
        self._engine = engine_factory(config, soundfont_path)
        self._engine.set_gain(0.65)
        self._tempo_bpm = config.tempo_bpm
        self._frame_position = 0
        self._tempo_epoch_frame = 0
        self._tempo_epoch_beat = 0.0
        self._section = DemoSection.MAIN
        self._section_start_beat = 0.0
        self._main_start_beat = 0.0
        self._ending_at_beat: float | None = None
        self._fill_at_beat: float | None = None
        self._fill_variation: int | None = None
        self._events: list[_QueuedAction] = []
        self._event_order = 0
        self._active_token: tuple[str, int] | None = None
        self._chord_signature: tuple[int, ChordQuality, int | None] | None = None
        self._silent = True
        self._closed = False
        self._channels = {
            track.midi_channel
            for variation in self._info.sections.values()
            for track in variation.tracks
            if track.midi_channel is not None
        }
        self._percussion_channels = {
            track.midi_channel
            for variation in self._info.sections.values()
            for track in variation.tracks
            if track.role in PERCUSSION_ROLES and track.midi_channel is not None
        }

    @property
    def tempo_bpm(self) -> int:
        return self._tempo_bpm

    @property
    def section(self) -> DemoSection:
        self._advance_state(self._beat_at_frame(self._frame_position))
        return self._section

    @property
    def position_ticks(self) -> int:
        return round(
            self._beat_at_frame(self._frame_position) * TRANSPORT_TICKS_PER_BEAT
        )

    @property
    def fill_variation(self) -> int | None:
        self._advance_state(self._beat_at_frame(self._frame_position))
        return self._fill_variation

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
        self._main_start_beat = 0.0
        self._ending_at_beat = None
        self._fill_at_beat = None
        self._fill_variation = None
        self._active_token = None
        self._chord_signature = None
        self._silent = True

    def start_main(self) -> None:
        self.reset()

    def start_intro(self) -> None:
        self.reset()
        self._section = DemoSection.INTRO

    def stop(self) -> None:
        self._all_sound_off()
        self._section = DemoSection.STOPPED
        self._ending_at_beat = None
        self._fill_at_beat = None
        self._fill_variation = None

    def request_ending(self) -> None:
        if self.section is DemoSection.STOPPED:
            return
        beat = self._beat_at_frame(self._frame_position)
        self._ending_at_beat = self._next_bar(beat)

    def request_fill(self, variation: int) -> None:
        if variation not in (1, 2):
            raise ValueError("fill variation must be 1 or 2")
        if self.section is not DemoSection.MAIN or self._ending_at_beat is not None:
            return
        beat = self._beat_at_frame(self._frame_position)
        self._fill_at_beat = self._next_bar(beat)
        self._fill_variation = variation

    def resume_if_stopped(self) -> None:
        if self.section is DemoSection.STOPPED:
            self.reset()

    def render(self, frame_count: int, chord: ChordState | None) -> bytes:
        if frame_count < 0:
            raise ValueError("frame_count cannot be negative")
        if frame_count == 0:
            return b""
        end_frame = self._frame_position + frame_count
        self._advance_state(self._beat_at_frame(self._frame_position))
        if self._section is DemoSection.STOPPED or chord is None:
            if not self._silent:
                self._all_sound_off()
            pcm = self._engine.render(frame_count)
            self._frame_position = end_frame
            self._advance_state(self._beat_at_frame(end_frame))
            return pcm
        signature = (chord.root_pitch_class, chord.quality, chord.bass_pitch_class)
        if signature != self._chord_signature:
            self._change_harmony()
            self._chord_signature = signature
        self._silent = False
        chunks: list[bytes] = []
        while self._frame_position < end_frame:
            beat = self._beat_at_frame(self._frame_position)
            self._advance_state(beat)
            if self._playback_stopped():
                chunks.append(self._engine.render(end_frame - self._frame_position))
                self._frame_position = end_frame
                break
            variation, origin, token = self._active_pattern(beat)
            if token != self._active_token:
                self._all_sound_off()
                self._active_token = token
            boundary_beat = self._next_boundary(beat, variation, origin)
            boundary_frame = min(
                end_frame,
                max(self._frame_position + 1, self._frame_at_beat(boundary_beat)),
            )
            self._queue_actions(
                variation, origin, beat, self._beat_at_frame(boundary_frame), chord
            )
            chunks.append(self._render_queued(self._frame_position, boundary_frame))
            self._frame_position = boundary_frame
        self._advance_state(self._beat_at_frame(end_frame))
        return b"".join(chunks)

    def close(self) -> None:
        if self._closed:
            return
        self._all_sound_off()
        self._engine.close()
        self._closed = True

    def _active_pattern(
        self, beat: float
    ) -> tuple[ChordVariation, float, tuple[str, int]]:
        if self._section is DemoSection.INTRO:
            return self._info.sections["intro"], self._section_start_beat, ("intro", 0)
        if self._section is DemoSection.ENDING:
            return (
                self._info.sections["ending"],
                self._section_start_beat,
                ("ending", 0),
            )
        if self._fill_at_beat is not None and beat >= self._fill_at_beat:
            name = f"fill_{self._fill_variation}"
            return self._info.sections[name], self._fill_at_beat, (name, 0)
        main = self._info.sections["main"]
        length = self._length_beats(main)
        cycle = max(0, math.floor((beat - self._main_start_beat) / length))
        origin = self._main_start_beat + cycle * length
        return main, origin, ("main", cycle)

    def _playback_stopped(self) -> bool:
        return self._section is DemoSection.STOPPED

    def _next_boundary(
        self, beat: float, variation: ChordVariation, origin: float
    ) -> float:
        candidates = [origin + self._length_beats(variation)]
        if self._ending_at_beat is not None and self._ending_at_beat > beat:
            candidates.append(self._ending_at_beat)
        if self._fill_at_beat is not None and self._fill_at_beat > beat:
            candidates.append(self._fill_at_beat)
        return min(candidates)

    def _advance_state(self, beat: float) -> None:
        epsilon = 1e-7
        if (
            self._ending_at_beat is not None
            and beat + epsilon >= self._ending_at_beat
            and self._section is not DemoSection.ENDING
        ):
            self._section = DemoSection.ENDING
            self._section_start_beat = self._ending_at_beat
            self._ending_at_beat = None
            self._fill_at_beat = None
            self._fill_variation = None
            self._active_token = None
        if self._section is DemoSection.INTRO:
            end = self._section_start_beat + self._length_beats(
                self._info.sections["intro"]
            )
            if beat + epsilon >= end:
                self._section = DemoSection.MAIN
                self._section_start_beat = end
                self._main_start_beat = end
                self._active_token = None
        if self._section is DemoSection.ENDING:
            end = self._section_start_beat + self._length_beats(
                self._info.sections["ending"]
            )
            if beat + epsilon >= end:
                self.stop()
                return
        if self._section is DemoSection.MAIN and self._fill_at_beat is not None:
            fill = self._info.sections[f"fill_{self._fill_variation}"]
            if beat + epsilon >= self._fill_at_beat + self._length_beats(fill):
                self._fill_at_beat = None
                self._fill_variation = None
                self._active_token = None

    def _queue_actions(
        self,
        variation: ChordVariation,
        origin: float,
        start_beat: float,
        end_beat: float,
        chord: ChordState,
    ) -> None:
        for action in _variation_actions(variation):
            absolute_beat = origin + action.tick / self._style.ticks_per_beat
            if start_beat - 1e-9 <= absolute_beat < end_beat - 1e-9:
                transformed = action
                if (
                    action.kind in {"note_on", "note_off"}
                    and action.role not in PERCUSSION_ROLES
                ):
                    transformed = _Action(
                        action.tick,
                        action.order,
                        action.channel,
                        action.role,
                        action.kind,
                        _adapt_note(action.first, self._info.anchor_pitch_class, chord),
                        action.second,
                    )
                self._event_order += 1
                heapq.heappush(
                    self._events,
                    _QueuedAction(
                        self._frame_at_beat(absolute_beat),
                        self._event_order,
                        transformed,
                    ),
                )

    def _render_queued(self, start_frame: int, end_frame: int) -> bytes:
        chunks: list[bytes] = []
        cursor = start_frame
        while self._events and self._events[0].frame < end_frame:
            event_frame = max(cursor, self._events[0].frame)
            if event_frame > cursor:
                chunks.append(self._engine.render(event_frame - cursor))
                cursor = event_frame
            while self._events and self._events[0].frame <= cursor:
                self._dispatch(heapq.heappop(self._events).action)
        if cursor < end_frame:
            chunks.append(self._engine.render(end_frame - cursor))
        return b"".join(chunks)

    def _dispatch(self, action: _Action) -> None:
        if action.kind == "note_on":
            self._engine.note_on(action.channel, action.first, action.second)
            self._silent = False
        elif action.kind == "note_off":
            self._engine.note_off(action.channel, action.first)
        elif action.kind == "control_change":
            self._engine.control_change(action.channel, action.first, action.second)
        elif action.kind == "program_change":
            bank = 128 if action.role in PERCUSSION_ROLES else 0
            program = 0 if action.role in PERCUSSION_ROLES else action.first
            self._engine.program_select(action.channel, bank, program)
        else:
            self._engine.pitch_bend(action.channel, action.first + 8192)

    def _change_harmony(self) -> None:
        self._events = [
            item
            for item in self._events
            if item.action.channel in self._percussion_channels
        ]
        heapq.heapify(self._events)
        for channel in self._channels - self._percussion_channels:
            self._engine.control_change(channel, 120, 0)
            self._engine.control_change(channel, 123, 0)

    def _all_sound_off(self) -> None:
        self._events.clear()
        for channel in self._channels:
            self._engine.control_change(channel, 120, 0)
            self._engine.control_change(channel, 123, 0)
            self._engine.pitch_bend(channel, 8192)
        self._silent = True

    def _beat_at_frame(self, frame: int) -> float:
        elapsed = frame - self._tempo_epoch_frame
        return self._tempo_epoch_beat + elapsed * self._tempo_bpm / (
            60 * self._config.sample_rate
        )

    def _frame_at_beat(self, beat: float) -> int:
        elapsed = beat - self._tempo_epoch_beat
        return self._tempo_epoch_frame + round(
            elapsed * 60 * self._config.sample_rate / self._tempo_bpm
        )

    def _length_beats(self, variation: ChordVariation) -> float:
        return variation.length_ticks / self._style.ticks_per_beat

    def _next_bar(self, beat: float) -> float:
        return (
            math.floor(beat / self._info.beats_per_bar) + 1
        ) * self._info.beats_per_bar


def _variation_actions(variation: ChordVariation) -> tuple[_Action, ...]:
    result: list[_Action] = []
    for track in variation.tracks:
        channel = track.midi_channel
        if channel is None:
            continue
        result.append(
            _Action(0, 2, channel, track.role, "program_change", track.program or 0)
        )
        for event in track.events:
            if isinstance(event, NoteEvent):
                result.append(
                    _Action(
                        event.start_tick,
                        4,
                        event.channel,
                        track.role,
                        "note_on",
                        event.note,
                        event.velocity,
                    )
                )
                result.append(
                    _Action(
                        event.start_tick + event.duration_ticks,
                        0,
                        event.channel,
                        track.role,
                        "note_off",
                        event.note,
                    )
                )
            elif isinstance(event, ControlChangeEvent) and event.controller not in {
                0,
                32,
            }:
                result.append(
                    _Action(
                        event.tick,
                        1,
                        event.channel,
                        track.role,
                        "control_change",
                        event.controller,
                        event.value,
                    )
                )
            elif isinstance(event, ProgramChangeEvent) and event.tick > 0:
                result.append(
                    _Action(
                        event.tick,
                        2,
                        event.channel,
                        track.role,
                        "program_change",
                        event.program,
                    )
                )
            elif isinstance(event, PitchBendEvent):
                result.append(
                    _Action(
                        event.tick,
                        3,
                        event.channel,
                        track.role,
                        "pitch_bend",
                        event.pitch,
                    )
                )
    return tuple(
        sorted(
            result, key=lambda item: (item.tick, item.order, item.channel, item.first)
        )
    )


def _adapt_note(note: int, anchor: int, chord: ChordState) -> int:
    root_delta = ((chord.root_pitch_class - anchor + 6) % 12) - 6
    source_interval = (note - anchor) % 12
    target_interval = source_interval
    if source_interval in {3, 4}:
        target_interval = (
            3 if chord.quality in {ChordQuality.MINOR, ChordQuality.DIMINISHED} else 4
        )
    elif source_interval in {6, 7}:
        target_interval = 6 if chord.quality is ChordQuality.DIMINISHED else 7
    elif source_interval in {10, 11}:
        target_interval = 10 if chord.quality is ChordQuality.DOMINANT_SEVENTH else 12
    return max(0, min(127, note + root_delta + target_interval - source_interval))
