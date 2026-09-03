"""Importer for Standard MIDI Files carrying KORG-style section markers."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mido  # type: ignore[import-untyped]

from ostinato.styles.importers.korg.markers import (
    StyleElementDescriptor,
    normalize_korg_marker,
    normalize_korg_track_role,
)
from ostinato.styles.models import (
    ChordVariation,
    ControlChangeEvent,
    JsonValue,
    NoteEvent,
    PitchBendEvent,
    ProgramChangeEvent,
    Style,
    StyleElement,
    StyleElementType,
    StyleEvent,
    StyleSource,
    StyleTrack,
)


class UnsupportedKorgStyleFormat(ValueError):
    """Raised when an input is not a supported marker-based MIDI export."""


@dataclass(frozen=True, slots=True)
class MarkerDiagnostic:
    """One marker-like MIDI meta event and its normalization result."""

    tick: int
    track_index: int
    raw: str
    descriptor: StyleElementDescriptor | None


@dataclass(frozen=True, slots=True)
class TrackDiagnostic:
    """Non-semantic facts useful when evaluating an unfamiliar export."""

    index: int
    name: str
    channels: tuple[int, ...]
    note_range: tuple[int, int] | None
    programs: tuple[int, ...]
    controllers: tuple[int, ...]
    sysex_count: int


@dataclass(frozen=True, slots=True)
class MidiStyleDiagnostics:
    """Structural diagnostics retained separately from playback data."""

    midi_format: int
    ticks_per_beat: int
    track_count: int
    markers: tuple[MarkerDiagnostic, ...]
    tracks: tuple[TrackDiagnostic, ...]
    tempo_changes: tuple[tuple[int, int], ...]
    time_signature_changes: tuple[tuple[int, int, int], ...]


@dataclass(frozen=True, slots=True)
class MidiStyleImportResult:
    """Imported style plus the facts used to interpret it."""

    style: Style
    diagnostics: MidiStyleDiagnostics


@dataclass(frozen=True, slots=True)
class _AbsoluteTrack:
    index: int
    name: str
    messages: tuple[tuple[int, Any], ...]
    end_tick: int


def import_korg_midi_style(
    path: Path,
    *,
    package: str | None = None,
) -> Style:
    """Import a marker-based MIDI file into the vendor-neutral model."""

    return inspect_korg_midi_style(path, package=package).style


def inspect_korg_midi_style(
    path: Path,
    *,
    package: str | None = None,
) -> MidiStyleImportResult:
    """Import and return detailed diagnostics for a marker-based MIDI file."""

    try:
        with path.open("rb") as source:
            header = source.read(4)
        if header != b"MThd":
            raise UnsupportedKorgStyleFormat(
                f"{path} is not a Standard MIDI File; "
                "native .STY parsing is not supported"
            )
        midi = mido.MidiFile(path)
    except UnsupportedKorgStyleFormat:
        raise
    except (OSError, EOFError, ValueError) as error:
        raise UnsupportedKorgStyleFormat(
            f"could not read MIDI input: {error}"
        ) from error
    if int(midi.type) == 2:
        raise UnsupportedKorgStyleFormat(
            "MIDI format 2 has independent track timelines and is not supported"
        )
    if int(midi.ticks_per_beat) <= 0:
        raise UnsupportedKorgStyleFormat(
            "SMPTE-timed MIDI is not supported for musical style import"
        )

    tracks = tuple(
        _absolute_track(index, track) for index, track in enumerate(midi.tracks)
    )
    markers = tuple(
        sorted(
            (
                MarkerDiagnostic(
                    tick,
                    track.index,
                    str(message.text),
                    normalize_korg_marker(str(message.text)),
                )
                for track in tracks
                for tick, message in track.messages
                if message.is_meta and message.type in {"marker", "cue_marker"}
            ),
            key=lambda marker: (marker.tick, marker.track_index),
        )
    )
    recognized = _recognized_boundaries(markers)
    if not recognized:
        raise UnsupportedKorgStyleFormat(
            "MIDI input contains no recognized KORG style section markers"
        )

    timeline_end = max((track.end_tick for track in tracks), default=0)
    variations_by_element: dict[StyleElementType, list[ChordVariation]] = defaultdict(
        list
    )
    element_order: list[StyleElementType] = []
    for index, marker in enumerate(recognized):
        descriptor = marker.descriptor
        assert descriptor is not None
        if descriptor.element_type not in variations_by_element:
            element_order.append(descriptor.element_type)
        end_tick = (
            recognized[index + 1].tick if index + 1 < len(recognized) else timeline_end
        )
        end_tick = max(marker.tick, end_tick)
        variations_by_element[descriptor.element_type].append(
            ChordVariation(
                number=descriptor.chord_variation,
                source_chord=None,
                length_ticks=end_tick - marker.tick,
                tracks=_style_tracks(tracks, marker.tick, end_tick),
                metadata={
                    "raw_marker": marker.raw,
                    "absolute_start_tick": marker.tick,
                },
            )
        )

    tempo_changes = _tempo_changes(tracks)
    time_signature_changes = _time_signature_changes(tracks)
    diagnostics = MidiStyleDiagnostics(
        midi_format=int(midi.type),
        ticks_per_beat=int(midi.ticks_per_beat),
        track_count=len(tracks),
        markers=markers,
        tracks=tuple(_track_diagnostic(track) for track in tracks),
        tempo_changes=tempo_changes,
        time_signature_changes=time_signature_changes,
    )
    unknown_markers: list[JsonValue] = [
        marker.raw for marker in markers if marker.descriptor is None
    ]
    style = Style(
        version=1,
        id=_style_id(path.stem),
        name=path.stem,
        source=StyleSource(
            manufacturer="KORG",
            source_format="standard_midi_with_korg_style_markers",
            original_file=path.name,
            package=package,
        ),
        ticks_per_beat=int(midi.ticks_per_beat),
        tempo_microseconds_per_beat=(tempo_changes[0][1] if tempo_changes else None),
        time_signature=(
            (time_signature_changes[0][1], time_signature_changes[0][2])
            if time_signature_changes
            else None
        ),
        elements=tuple(
            StyleElement(
                type=element_type,
                name=element_type.value.replace("_", " ").title(),
                chord_variations=tuple(variations_by_element[element_type]),
            )
            for element_type in element_order
        ),
        metadata={
            "midi_format": int(midi.type),
            "unknown_markers": unknown_markers,
            "source_chord_status": "unknown",
            "origin_authentication": "not_performed",
            "midi_channel_numbering": "zero_based",
            "midi_program_numbering": "zero_based",
        },
    )
    return MidiStyleImportResult(style, diagnostics)


def diagnostics_to_dict(diagnostics: MidiStyleDiagnostics) -> dict[str, JsonValue]:
    """Serialize diagnostics for CLI JSON and reproducible tests."""

    return {
        "midi_format": diagnostics.midi_format,
        "ticks_per_beat": diagnostics.ticks_per_beat,
        "track_count": diagnostics.track_count,
        "markers": [
            {
                "tick": marker.tick,
                "track_index": marker.track_index,
                "raw": marker.raw,
                "element": (
                    marker.descriptor.element_type.value
                    if marker.descriptor is not None
                    else None
                ),
                "chord_variation": (
                    marker.descriptor.chord_variation
                    if marker.descriptor is not None
                    else None
                ),
            }
            for marker in diagnostics.markers
        ],
        "tracks": [
            {
                "index": track.index,
                "name": track.name,
                "channels": list(track.channels),
                "note_range": (
                    list(track.note_range) if track.note_range is not None else None
                ),
                "programs": list(track.programs),
                "controllers": list(track.controllers),
                "sysex_count": track.sysex_count,
            }
            for track in diagnostics.tracks
        ],
        "tempo_changes": [list(change) for change in diagnostics.tempo_changes],
        "time_signature_changes": [
            list(change) for change in diagnostics.time_signature_changes
        ],
    }


def _absolute_track(index: int, track: Any) -> _AbsoluteTrack:
    tick = 0
    name = f"Track {index}"
    messages: list[tuple[int, Any]] = []
    for message in track:
        tick += int(message.time)
        messages.append((tick, message))
        if message.is_meta and message.type == "track_name":
            name = str(message.name)
    return _AbsoluteTrack(index, name, tuple(messages), tick)


def _style_tracks(
    tracks: tuple[_AbsoluteTrack, ...],
    start_tick: int,
    end_tick: int,
) -> tuple[StyleTrack, ...]:
    result: list[StyleTrack] = []
    for track in tracks:
        style_track = _style_track(track, start_tick, end_tick)
        if style_track is not None:
            result.append(style_track)
    return tuple(result)


def _style_track(
    track: _AbsoluteTrack,
    start_tick: int,
    end_tick: int,
) -> StyleTrack | None:
    segment_messages = [
        (tick, message)
        for tick, message in track.messages
        if start_tick <= tick <= end_tick and not message.is_meta
    ]
    channel_messages = [
        message
        for tick, message in segment_messages
        if tick < end_tick and hasattr(message, "channel")
    ]
    if not channel_messages:
        return None
    channels = sorted({int(message.channel) for message in channel_messages})
    events: list[StyleEvent] = []
    active_notes: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    clipped_notes = 0
    for tick, message in segment_messages:
        relative_tick = tick - start_tick
        if tick < end_tick and message.type == "note_on" and int(message.velocity) > 0:
            active_notes[(int(message.channel), int(message.note))].append(
                (relative_tick, int(message.velocity))
            )
        elif message.type == "note_off" or (
            message.type == "note_on" and int(message.velocity) == 0
        ):
            key = (int(message.channel), int(message.note))
            if active_notes[key]:
                note_start, velocity = active_notes[key].pop(0)
                events.append(
                    NoteEvent(
                        note_start,
                        max(0, relative_tick - note_start),
                        key[1],
                        velocity,
                        key[0],
                    )
                )
        elif tick < end_tick and message.type == "control_change":
            events.append(
                ControlChangeEvent(
                    relative_tick,
                    int(message.control),
                    int(message.value),
                    int(message.channel),
                )
            )
        elif tick < end_tick and message.type == "program_change":
            events.append(
                ProgramChangeEvent(
                    relative_tick,
                    int(message.program),
                    int(message.channel),
                )
            )
        elif tick < end_tick and message.type == "pitchwheel":
            events.append(
                PitchBendEvent(
                    relative_tick,
                    int(message.pitch),
                    int(message.channel),
                )
            )
    for (channel, note), starts in active_notes.items():
        for note_start, velocity in starts:
            clipped_notes += 1
            events.append(
                NoteEvent(
                    note_start,
                    max(0, end_tick - start_tick - note_start),
                    note,
                    velocity,
                    channel,
                )
            )
    events.sort(key=_event_sort_key)
    segment_program = next(
        (event.program for event in events if isinstance(event, ProgramChangeEvent)),
        None,
    )
    segment_bank_msb = next(
        (
            event.value
            for event in events
            if isinstance(event, ControlChangeEvent) and event.controller == 0
        ),
        None,
    )
    segment_bank_lsb = next(
        (
            event.value
            for event in events
            if isinstance(event, ControlChangeEvent) and event.controller == 32
        ),
        None,
    )
    if len(channels) == 1:
        channel = channels[0]
        program = _latest_channel_setting(
            track, start_tick, channel, "program_change", "program"
        )
        bank_msb = _latest_controller_value(track, start_tick, channel, 0)
        bank_lsb = _latest_controller_value(track, start_tick, channel, 32)
    else:
        program = None
        bank_msb = None
        bank_lsb = None
    program = program if program is not None else segment_program
    bank_msb = bank_msb if bank_msb is not None else segment_bank_msb
    bank_lsb = bank_lsb if bank_lsb is not None else segment_bank_lsb
    channel_values: list[JsonValue] = [channel for channel in channels]
    return StyleTrack(
        role=normalize_korg_track_role(track.name),
        source_name=track.name,
        midi_channel=channels[0] if len(channels) == 1 else None,
        program=program,
        bank_msb=bank_msb,
        bank_lsb=bank_lsb,
        events=tuple(events),
        metadata={
            "source_track_index": track.index,
            "channels": channel_values,
            "clipped_note_count": clipped_notes,
        },
    )


def _event_sort_key(event: StyleEvent) -> tuple[int, str]:
    tick = event.start_tick if isinstance(event, NoteEvent) else event.tick
    return tick, type(event).__name__


def _recognized_boundaries(
    markers: tuple[MarkerDiagnostic, ...],
) -> tuple[MarkerDiagnostic, ...]:
    boundaries: list[MarkerDiagnostic] = []
    descriptors_at_tick: dict[int, set[tuple[StyleElementType, int | None]]] = (
        defaultdict(set)
    )
    for marker in markers:
        descriptor = marker.descriptor
        if descriptor is None:
            continue
        key = (descriptor.element_type, descriptor.chord_variation)
        if key in descriptors_at_tick[marker.tick]:
            continue
        if descriptors_at_tick[marker.tick]:
            raise UnsupportedKorgStyleFormat(
                f"conflicting style section markers at tick {marker.tick}"
            )
        descriptors_at_tick[marker.tick].add(key)
        boundaries.append(marker)
    return tuple(boundaries)


def _latest_channel_setting(
    track: _AbsoluteTrack,
    tick_limit: int,
    channel: int,
    message_type: str,
    attribute: str,
) -> int | None:
    value: int | None = None
    for tick, message in track.messages:
        if tick > tick_limit:
            break
        if (
            not message.is_meta
            and message.type == message_type
            and int(message.channel) == channel
        ):
            value = int(getattr(message, attribute))
    return value


def _latest_controller_value(
    track: _AbsoluteTrack,
    tick_limit: int,
    channel: int,
    controller: int,
) -> int | None:
    value: int | None = None
    for tick, message in track.messages:
        if tick > tick_limit:
            break
        if (
            not message.is_meta
            and message.type == "control_change"
            and int(message.channel) == channel
            and int(message.control) == controller
        ):
            value = int(message.value)
    return value


def _track_diagnostic(track: _AbsoluteTrack) -> TrackDiagnostic:
    channel_messages = [
        message
        for _, message in track.messages
        if not message.is_meta and hasattr(message, "channel")
    ]
    notes = [
        int(message.note)
        for message in channel_messages
        if message.type in {"note_on", "note_off"}
    ]
    return TrackDiagnostic(
        index=track.index,
        name=track.name,
        channels=tuple(sorted({int(message.channel) for message in channel_messages})),
        note_range=(min(notes), max(notes)) if notes else None,
        programs=tuple(
            sorted(
                {
                    int(message.program)
                    for message in channel_messages
                    if message.type == "program_change"
                }
            )
        ),
        controllers=tuple(
            sorted(
                {
                    int(message.control)
                    for message in channel_messages
                    if message.type == "control_change"
                }
            )
        ),
        sysex_count=sum(1 for _, message in track.messages if message.type == "sysex"),
    )


def _tempo_changes(tracks: tuple[_AbsoluteTrack, ...]) -> tuple[tuple[int, int], ...]:
    return tuple(
        sorted(
            (
                (tick, int(message.tempo))
                for track in tracks
                for tick, message in track.messages
                if message.is_meta and message.type == "set_tempo"
            ),
            key=lambda change: change[0],
        )
    )


def _time_signature_changes(
    tracks: tuple[_AbsoluteTrack, ...],
) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        sorted(
            (
                (tick, int(message.numerator), int(message.denominator))
                for track in tracks
                for tick, message in track.messages
                if message.is_meta and message.type == "time_signature"
            ),
            key=lambda change: change[0],
        )
    )


def _style_id(name: str) -> str:
    identifier = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return f"korg-{identifier or 'imported-style'}"
