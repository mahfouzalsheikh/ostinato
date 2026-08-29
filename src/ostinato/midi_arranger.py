"""Absolute-deadline MIDI accompaniment for the FR-4X sound module."""

from __future__ import annotations

import heapq
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ostinato.computer_audio import DEMO_STYLES, DemoSection
from ostinato.domain import ChordQuality, ChordState
from ostinato.realtime_midi import MidiService

TICKS_PER_QUARTER = 96
SECTION_BARS = 4
KICK_NOTE = 36
SNARE_NOTE = 38
CLOSED_HIHAT_NOTE = 42


@dataclass(frozen=True, slots=True)
class MidiRouting:
    """User-confirmed FR-4X receive channels for accompaniment parts."""

    bass_channel: int
    chord_channel: int
    drum_channel: int

    def __post_init__(self) -> None:
        channels = (self.bass_channel, self.chord_channel, self.drum_channel)
        if any(not 1 <= channel <= 16 for channel in channels):
            raise ValueError("arranger MIDI channels must be from 1 through 16")
        if self.drum_channel in (self.bass_channel, self.chord_channel):
            raise ValueError("the drum channel must differ from bass and chord")


@dataclass(frozen=True, slots=True, order=True)
class PlannedMessage:
    """One immutable MIDI message or internal bar-boundary marker."""

    tick: int
    order: int
    data: tuple[int, ...] | None = field(compare=False)


_INTERVALS = {
    ChordQuality.MAJOR: (0, 4, 7),
    ChordQuality.MINOR: (0, 3, 7),
    ChordQuality.DOMINANT_SEVENTH: (0, 4, 7, 10),
    ChordQuality.DIMINISHED: (0, 3, 6),
}


def plan_style_bar(
    *,
    style_id: str,
    section: DemoSection,
    section_bar: int,
    start_tick: int,
    chord: ChordState | None,
    routing: MidiRouting,
) -> tuple[PlannedMessage, ...]:
    """Plan one bar without clocks, sleeps, or output side effects."""

    if style_id not in DEMO_STYLES:
        raise ValueError(f"unknown arranger style: {style_id}")
    beats = DEMO_STYLES[style_id].beats_per_bar
    bar_ticks = beats * TICKS_PER_QUARTER
    messages: list[PlannedMessage] = []
    sequence = 0

    def note(
        beat: float,
        duration: float,
        channel: int,
        midi_note: int,
        velocity: int,
    ) -> None:
        nonlocal sequence
        on_tick = start_tick + round(beat * TICKS_PER_QUARTER)
        off_tick = on_tick + max(1, round(duration * TICKS_PER_QUARTER))
        sequence += 1
        messages.append(
            PlannedMessage(
                on_tick, (sequence * 2) + 1, (0x90 | (channel - 1), midi_note, velocity)
            )
        )
        messages.append(
            PlannedMessage(off_tick, sequence * 2, (0x80 | (channel - 1), midi_note, 0))
        )

    intro_level = section_bar + 1 if section is DemoSection.INTRO else SECTION_BARS
    ending_level = (
        SECTION_BARS - section_bar if section is DemoSection.ENDING else SECTION_BARS
    )
    level = min(intro_level, ending_level)

    if chord is not None:
        root = chord.root_pitch_class
        bass_root = (
            chord.bass_pitch_class if chord.bass_pitch_class is not None else root
        )
        bass_pattern: tuple[tuple[float, int], ...]
        chord_onsets: tuple[float, ...]
        if style_id == "modern_tango":
            bass_pattern = ((0.0, 0), (1.5, 7), (3.0, 12))
            chord_onsets = (0.5, 2.0, 3.5)
        else:
            bass_pattern = ((0.0, 0), (2.0, 7))
            chord_onsets = (1.0, 2.0)

        if section is DemoSection.ENDING and section_bar == SECTION_BARS - 1:
            bass_pattern = ((0.0, 0),)
            chord_onsets = (0.0,)
        if level >= 2:
            for beat, interval in bass_pattern:
                note(beat, 0.38, routing.bass_channel, 36 + bass_root + interval, 92)
        intervals = _INTERVALS[chord.quality]
        chord_duration = (
            beats - 0.1 if section is DemoSection.ENDING and section_bar == 3 else 0.34
        )
        for beat in chord_onsets:
            for interval in intervals:
                note(
                    beat,
                    chord_duration,
                    routing.chord_channel,
                    60 + root + interval,
                    76,
                )

    if level >= 3:
        kicks: tuple[float, ...]
        snares: tuple[float, ...]
        hats: tuple[float, ...]
        if style_id == "modern_tango":
            kicks = (0.0, 1.5, 3.0)
            snares = (0.5, 2.0, 3.5)
            hats = tuple(index / 2 for index in range(8))
        else:
            kicks = (0.0,)
            snares = (1.0, 2.0)
            hats = (0.0, 1.0, 2.0)
        if section is DemoSection.ENDING and section_bar >= 2:
            hats = ()
        for beat in kicks:
            note(beat, 0.12, routing.drum_channel, KICK_NOTE, 92)
        for beat in snares:
            note(beat, 0.12, routing.drum_channel, SNARE_NOTE, 80)
        for beat in hats:
            note(beat, 0.08, routing.drum_channel, CLOSED_HIHAT_NOTE, 58)

    messages.append(PlannedMessage(start_tick + bar_ticks, 1_000_000, None))
    return tuple(sorted(messages))


class MidiArrangerOutput:
    """Own transport planning and dispatch MIDI with absolute deadlines."""

    def __init__(
        self,
        midi: MidiService,
        *,
        clock: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self._midi = midi
        self._clock = clock
        self._owner = object()
        self._condition = threading.Condition()
        self._closed = False
        self._playing = False
        self._section = DemoSection.STOPPED
        self._section_bar = 0
        self._ending_requested = False
        self._style_id = "modern_tango"
        self._tempo_bpm = DEMO_STYLES[self._style_id].default_tempo_bpm
        self._chord: ChordState | None = None
        self._routing: MidiRouting | None = None
        self._events: list[PlannedMessage] = []
        self._next_bar_tick = 0
        self._epoch_ns = 0
        self._epoch_tick = 0
        self._error: str | None = None
        self._thread = threading.Thread(
            target=self._run,
            name="ostinato-midi-arranger",
            daemon=True,
        )
        self._thread.start()

    @property
    def section(self) -> DemoSection:
        with self._condition:
            return self._section

    @property
    def error(self) -> str | None:
        with self._condition:
            return self._error

    def configure_routing(self, routing: MidiRouting | None) -> None:
        with self._condition:
            if self._playing:
                raise RuntimeError("stop the arranger before changing MIDI routing")
            self._routing = routing

    def select_style(self, style_id: str) -> None:
        if style_id not in DEMO_STYLES:
            raise ValueError(f"unknown arranger style: {style_id}")
        with self._condition:
            self._style_id = style_id
            self._condition.notify_all()

    def set_tempo(self, tempo_bpm: int) -> None:
        now = self._clock()
        with self._condition:
            if self._playing:
                current_tick = self._tick_at_ns_locked(now)
                self._epoch_ns = now
                self._epoch_tick = current_tick
            self._tempo_bpm = tempo_bpm
            self._condition.notify_all()

    def set_chord(self, chord: ChordState | None) -> None:
        with self._condition:
            self._chord = chord

    def start_main(self) -> None:
        self._start(DemoSection.MAIN)

    def start_intro(self) -> None:
        self._start(DemoSection.INTRO)

    def request_ending(self) -> None:
        with self._condition:
            if self._playing:
                self._ending_requested = True

    def stop(self) -> None:
        with self._condition:
            self._stop_locked()
            self._condition.notify_all()
        self._midi.release(self._owner)

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._stop_locked()
            self._condition.notify_all()
        self._thread.join(timeout=2)
        self._midi.release(self._owner)

    def _start(self, section: DemoSection) -> None:
        with self._condition:
            if self._routing is None:
                raise RuntimeError(
                    "configure and confirm FR-4X arranger channels first"
                )
            self._events.clear()
            self._playing = True
            self._section = section
            self._section_bar = 0
            self._ending_requested = False
            self._next_bar_tick = 0
            self._epoch_ns = self._clock()
            self._epoch_tick = 0
            self._error = None
            self._plan_next_bar_locked()
            self._condition.notify_all()

    def _run(self) -> None:
        while True:
            dispatch: tuple[int, ...] | None = None
            release = False
            with self._condition:
                if self._closed:
                    return
                if not self._playing or not self._events:
                    self._condition.wait()
                    continue
                event = self._events[0]
                deadline = self._deadline_for_tick_locked(event.tick)
                remaining_ns = deadline - self._clock()
                if remaining_ns > 0:
                    self._condition.wait(remaining_ns / 1_000_000_000)
                    continue
                heapq.heappop(self._events)
                if event.data is None:
                    release = self._advance_boundary_locked(event.tick)
                else:
                    dispatch = event.data
            if dispatch is not None:
                try:
                    self._midi.send(dispatch, owner=self._owner)
                except Exception as error:
                    with self._condition:
                        self._error = str(error)
                        self._stop_locked()
                    self._midi.release(self._owner)
            if release:
                self._midi.release(self._owner)

    def _advance_boundary_locked(self, boundary_tick: int) -> bool:
        self._section_bar += 1
        if self._section is DemoSection.INTRO and self._section_bar >= SECTION_BARS:
            self._section = DemoSection.MAIN
            self._section_bar = 0
        elif self._section is DemoSection.ENDING and self._section_bar >= SECTION_BARS:
            self._stop_locked()
            return True
        elif self._section is DemoSection.MAIN and self._ending_requested:
            self._section = DemoSection.ENDING
            self._section_bar = 0
            self._ending_requested = False
        self._next_bar_tick = boundary_tick
        self._plan_next_bar_locked()
        return False

    def _plan_next_bar_locked(self) -> None:
        routing = self._routing
        if routing is None:
            self._stop_locked()
            return
        for event in plan_style_bar(
            style_id=self._style_id,
            section=self._section,
            section_bar=self._section_bar,
            start_tick=self._next_bar_tick,
            chord=self._chord,
            routing=routing,
        ):
            heapq.heappush(self._events, event)

    def _stop_locked(self) -> None:
        self._events.clear()
        self._playing = False
        self._section = DemoSection.STOPPED
        self._ending_requested = False

    def _tick_at_ns_locked(self, timestamp_ns: int) -> int:
        elapsed_ns = max(0, timestamp_ns - self._epoch_ns)
        elapsed_ticks = (
            elapsed_ns * self._tempo_bpm * TICKS_PER_QUARTER // 60_000_000_000
        )
        return self._epoch_tick + elapsed_ticks

    def _deadline_for_tick_locked(self, tick: int) -> int:
        remaining_ticks = tick - self._epoch_tick
        return self._epoch_ns + (
            remaining_ticks * 60_000_000_000 // (self._tempo_bpm * TICKS_PER_QUARTER)
        )
