"""Offline listening renders for imported vendor-neutral styles."""

from __future__ import annotations

import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ostinato.computer_audio import DemoAudioConfig
from ostinato.soundfont_audio import FluidSynthEngine
from ostinato.styles.models import (
    ChordVariation,
    ControlChangeEvent,
    NoteEvent,
    ProgramChangeEvent,
    Style,
    StyleElementType,
    StyleEvent,
    StyleTrackRole,
)


class OfflineStyleSynth(Protocol):
    """Minimal synth operations needed for a deterministic style render."""

    def program_select(self, channel: int, bank: int, program: int) -> None: ...

    def control_change(self, channel: int, controller: int, value: int) -> None: ...

    def pitch_bend(self, channel: int, value: int) -> None: ...

    def set_gain(self, gain: float) -> None: ...

    def note_on(self, channel: int, note: int, velocity: int) -> None: ...

    def note_off(self, channel: int, note: int) -> None: ...

    def render(self, frame_count: int) -> bytes: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class OfflineStyleRenderReport:
    """Facts about one generated listening reference."""

    output_path: Path
    element_type: StyleElementType
    chord_variation: int
    sample_rate: int
    frame_count: int
    note_count: int
    tempo_microseconds_per_beat: int
    gm_program_approximation: bool
    source_pitch_transposition: str

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.sample_rate


@dataclass(frozen=True, slots=True)
class _PlaybackEvent:
    tick: int
    order: int
    channel: int
    kind: str
    first: int
    second: int = 0


def render_style_variation_to_wav(
    style: Style,
    output_path: Path,
    soundfont_path: Path,
    *,
    element_type: StyleElementType = StyleElementType.VARIATION_1,
    chord_variation: int = 1,
    tempo_bpm: int | None = None,
    sample_rate: int = 48_000,
    tail_seconds: float = 0.5,
    engine_factory: Callable[[DemoAudioConfig, str], OfflineStyleSynth] = (
        FluidSynthEngine
    ),
) -> OfflineStyleRenderReport:
    """Render one imported Chord Variation at its stored source pitches.

    The exported KORG bank/program identifiers are preserved in the style
    document but do not identify patches in a General MIDI SoundFont. This
    listening render therefore uses bank 0 with the exported program number
    for melodic tracks and a GM percussion bank for both percussion roles.
    """

    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if tail_seconds < 0:
        raise ValueError("tail_seconds cannot be negative")
    if tempo_bpm is not None and tempo_bpm <= 0:
        raise ValueError("tempo_bpm must be positive")
    variation = _find_variation(style, element_type, chord_variation)
    tempo = (
        round(60_000_000 / tempo_bpm)
        if tempo_bpm is not None
        else style.tempo_microseconds_per_beat
    )
    if tempo is None:
        raise ValueError("style has no declared tempo; pass tempo_bpm explicitly")

    config = DemoAudioConfig(
        tempo_bpm=max(1, round(60_000_000 / tempo)),
        sample_rate=sample_rate,
        chunk_frames=max(1, sample_rate // 100),
    )
    engine = engine_factory(config, str(soundfont_path))
    events = _playback_events(variation)
    channels = sorted(
        {
            track.midi_channel
            for track in variation.tracks
            if track.midi_channel is not None
        }
    )
    engine.set_gain(0.65)
    try:
        for track in variation.tracks:
            channel = track.midi_channel
            if channel is None:
                continue
            if track.role in {StyleTrackRole.DRUM, StyleTrackRole.PERCUSSION}:
                engine.program_select(channel, 128, 0)
            else:
                engine.program_select(channel, 0, track.program or 0)

        chunks: list[bytes] = []
        frame_cursor = 0
        for event in events:
            event_frame = _frame_at_tick(
                event.tick,
                style.ticks_per_beat,
                tempo,
                sample_rate,
            )
            if event_frame > frame_cursor:
                chunks.append(engine.render(event_frame - frame_cursor))
                frame_cursor = event_frame
            _dispatch(engine, event)
        end_frame = _frame_at_tick(
            variation.length_ticks,
            style.ticks_per_beat,
            tempo,
            sample_rate,
        )
        if end_frame > frame_cursor:
            chunks.append(engine.render(end_frame - frame_cursor))
            frame_cursor = end_frame
        for channel in channels:
            engine.control_change(channel, 120, 0)
        tail_frames = round(tail_seconds * sample_rate)
        if tail_frames:
            chunks.append(engine.render(tail_frames))
            frame_cursor += tail_frames
        pcm = b"".join(chunks)
    finally:
        engine.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm)
    return OfflineStyleRenderReport(
        output_path=output_path,
        element_type=element_type,
        chord_variation=chord_variation,
        sample_rate=sample_rate,
        frame_count=frame_cursor,
        note_count=sum(
            isinstance(event, NoteEvent)
            for track in variation.tracks
            for event in track.events
        ),
        tempo_microseconds_per_beat=tempo,
        gm_program_approximation=True,
        source_pitch_transposition="none",
    )


def _find_variation(
    style: Style, element_type: StyleElementType, number: int
) -> ChordVariation:
    for element in style.elements:
        if element.type is not element_type:
            continue
        for variation in element.chord_variations:
            if variation.number == number:
                return variation
        break
    raise ValueError(f"style has no {element_type.value} Chord Variation {number}")


def _playback_events(variation: ChordVariation) -> tuple[_PlaybackEvent, ...]:
    result: list[_PlaybackEvent] = []
    for track in variation.tracks:
        for event in track.events:
            result.extend(_expand_event(event))
    return tuple(
        sorted(
            result,
            key=lambda event: (event.tick, event.order, event.channel, event.first),
        )
    )


def _expand_event(event: StyleEvent) -> tuple[_PlaybackEvent, ...]:
    if isinstance(event, NoteEvent):
        return (
            _PlaybackEvent(
                event.start_tick + event.duration_ticks,
                0,
                event.channel,
                "note_off",
                event.note,
            ),
            _PlaybackEvent(
                event.start_tick,
                4,
                event.channel,
                "note_on",
                event.note,
                event.velocity,
            ),
        )
    if isinstance(event, ControlChangeEvent):
        if event.controller in {0, 32}:
            return ()
        return (
            _PlaybackEvent(
                event.tick,
                1,
                event.channel,
                "control_change",
                event.controller,
                event.value,
            ),
        )
    if isinstance(event, ProgramChangeEvent):
        if event.tick == 0:
            return ()
        return (
            _PlaybackEvent(
                event.tick,
                2,
                event.channel,
                "program_change",
                event.program,
            ),
        )
    return (
        _PlaybackEvent(
            event.tick,
            3,
            event.channel,
            "pitch_bend",
            event.pitch + 8192,
        ),
    )


def _dispatch(engine: OfflineStyleSynth, event: _PlaybackEvent) -> None:
    if event.kind == "note_off":
        engine.note_off(event.channel, event.first)
    elif event.kind == "note_on":
        engine.note_on(event.channel, event.first, event.second)
    elif event.kind == "control_change":
        engine.control_change(event.channel, event.first, event.second)
    elif event.kind == "program_change":
        engine.program_select(event.channel, 0, event.first)
    else:
        engine.pitch_bend(event.channel, event.first)


def _frame_at_tick(
    tick: int,
    ticks_per_beat: int,
    tempo_microseconds_per_beat: int,
    sample_rate: int,
) -> int:
    numerator = tick * tempo_microseconds_per_beat * sample_rate
    denominator = ticks_per_beat * 1_000_000
    return (numerator + (denominator // 2)) // denominator
