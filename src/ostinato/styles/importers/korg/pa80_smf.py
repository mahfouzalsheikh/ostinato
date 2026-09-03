"""Import per-chord-variation SMFs exported by KORG's Pa80 utility."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mido  # type: ignore[import-untyped]

from ostinato.styles.importers.korg.midi_style_importer import (
    UnsupportedKorgStyleFormat,
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
    StyleTrackRole,
)

_VARIATION_FILENAME = re.compile(r"v(?P<element>[1-4])cv(?P<cv>[1-6])\.mid")
_OTHER_FILENAME = re.compile(r"(?P<prefix>[ife])(?P<element>[1-2])cv(?P<cv>[1-2])\.mid")
_ELEMENT_ORDER = (
    StyleElementType.VARIATION_1,
    StyleElementType.VARIATION_2,
    StyleElementType.VARIATION_3,
    StyleElementType.VARIATION_4,
    StyleElementType.INTRO_1,
    StyleElementType.INTRO_2,
    StyleElementType.FILL_1,
    StyleElementType.FILL_2,
    StyleElementType.ENDING_1,
    StyleElementType.ENDING_2,
)
_CHANNEL_ROLES = {
    8: StyleTrackRole.BASS,
    9: StyleTrackRole.DRUM,
    10: StyleTrackRole.PERCUSSION,
    11: StyleTrackRole.ACC1,
    12: StyleTrackRole.ACC2,
    13: StyleTrackRole.ACC3,
    14: StyleTrackRole.ACC4,
    15: StyleTrackRole.ACC5,
}
_ROLE_NAMES = {
    StyleTrackRole.BASS: "Bass",
    StyleTrackRole.DRUM: "Drum",
    StyleTrackRole.PERCUSSION: "Percussion",
    StyleTrackRole.ACC1: "Accompaniment 1",
    StyleTrackRole.ACC2: "Accompaniment 2",
    StyleTrackRole.ACC3: "Accompaniment 3",
    StyleTrackRole.ACC4: "Accompaniment 4",
    StyleTrackRole.ACC5: "Accompaniment 5",
}
_SUPPORTED_CHANNEL_MESSAGES = {
    "control_change",
    "note_off",
    "note_on",
    "pitchwheel",
    "program_change",
}
_STYLE_ID = re.compile(r"korg-[a-z0-9]+(?:-[a-z0-9]+)*")


@dataclass(frozen=True, slots=True)
class Pa80ChordVariationDiagnostic:
    """Observed structure of one utility-exported chord variation."""

    filename: str
    element_type: StyleElementType
    chord_variation: int
    length_ticks: int
    channels: tuple[int, ...]
    message_counts: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class Pa80StyleDiagnostics:
    """Structural facts collected across one directory of Pa80 SMFs."""

    ticks_per_beat: int
    time_signature: tuple[int, int]
    declared_tempos: tuple[int, ...]
    files: tuple[Pa80ChordVariationDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class Pa80StyleImportResult:
    """Imported style and reproducible diagnostics for its source files."""

    style: Style
    diagnostics: Pa80StyleDiagnostics


@dataclass(frozen=True, slots=True)
class _VariationFile:
    descriptor: tuple[StyleElementType, int]
    path: Path
    ticks_per_beat: int
    time_signature: tuple[int, int]
    tempo: int | None
    length_ticks: int
    messages: tuple[tuple[int, Any], ...]


def inspect_pa80_smf_directory(
    path: Path,
    *,
    style_name: str | None = None,
    original_file: str | None = None,
    package: str | None = None,
    style_id: str | None = None,
    library_group: str | None = None,
) -> Pa80StyleImportResult:
    """Import a directory produced by Pa80 Style to MIDI 1.06.

    The legacy utility exports one format-0 SMF per Chord Variation. KORG's
    documented lowercase filenames provide the section boundary, while its
    documented MIDI-channel table provides the track roles.
    """

    if not path.is_dir():
        raise UnsupportedKorgStyleFormat(
            f"Pa80 Chord Variation input is not a directory: {path}"
        )
    midi_paths = tuple(sorted(path.glob("*.mid")))
    if not midi_paths:
        raise UnsupportedKorgStyleFormat(
            f"Pa80 Chord Variation directory contains no .mid files: {path}"
        )

    variations: list[_VariationFile] = []
    seen: set[tuple[StyleElementType, int]] = set()
    for midi_path in midi_paths:
        descriptor = _descriptor_from_filename(midi_path.name)
        if descriptor is None:
            raise UnsupportedKorgStyleFormat(
                "Pa80 Chord Variation filename does not follow KORG's "
                f"lowercase EnCVn convention: {midi_path.name}"
            )
        if descriptor in seen:
            raise UnsupportedKorgStyleFormat(
                f"duplicate Pa80 Chord Variation: {midi_path.name}"
            )
        seen.add(descriptor)
        variations.append(_read_variation(midi_path, descriptor))

    ticks_per_beat = variations[0].ticks_per_beat
    meters = {variation.time_signature for variation in variations}
    resolutions = {variation.ticks_per_beat for variation in variations}
    if len(resolutions) != 1:
        raise UnsupportedKorgStyleFormat(
            "Pa80 Chord Variation files use inconsistent tick resolutions"
        )
    if len(meters) != 1:
        raise UnsupportedKorgStyleFormat(
            "Pa80 Chord Variation files use inconsistent time signatures"
        )
    time_signature = variations[0].time_signature

    by_element: dict[StyleElementType, list[ChordVariation]] = defaultdict(list)
    diagnostics: list[Pa80ChordVariationDiagnostic] = []
    for variation in variations:
        element_type, number = variation.descriptor
        channels = tuple(
            sorted(
                {
                    int(message.channel)
                    for _, message in variation.messages
                    if hasattr(message, "channel")
                }
            )
        )
        tracks = tuple(_channel_track(variation, channel) for channel in channels)
        by_element[element_type].append(
            ChordVariation(
                number=number,
                source_chord=None,
                length_ticks=variation.length_ticks,
                tracks=tracks,
                metadata={
                    "source_midi_file": variation.path.name,
                    "source_chord_status": "not_present_in_smf",
                    "declared_tempo_microseconds_per_beat": variation.tempo,
                    "time_signature": list(variation.time_signature),
                },
            )
        )
        counts = Counter(
            message.type for _, message in variation.messages if not message.is_meta
        )
        message_counts: dict[str, JsonValue] = {
            str(name): int(count) for name, count in sorted(counts.items())
        }
        diagnostics.append(
            Pa80ChordVariationDiagnostic(
                filename=variation.path.name,
                element_type=element_type,
                chord_variation=number,
                length_ticks=variation.length_ticks,
                channels=channels,
                message_counts=message_counts,
            )
        )

    name = (style_name or path.name).strip()
    if not name:
        raise UnsupportedKorgStyleFormat("style name cannot be empty")
    identifier = style_id or _style_id(name)
    if _STYLE_ID.fullmatch(identifier) is None:
        raise UnsupportedKorgStyleFormat(
            "Pa80 style id must use the korg-lowercase-slug form"
        )
    group = library_group.strip() if library_group is not None else None
    if library_group is not None and not group:
        raise UnsupportedKorgStyleFormat("library group cannot be empty")
    declared_tempos = tuple(
        sorted(
            {variation.tempo for variation in variations if variation.tempo is not None}
        )
    )
    tempo = declared_tempos[0] if len(declared_tempos) == 1 else None
    style = Style(
        version=1,
        id=identifier,
        name=name,
        source=StyleSource(
            manufacturer="KORG",
            source_format="pa80_style_to_midi_1.06_chord_variations",
            original_file=original_file or path.name,
            package=package,
        ),
        ticks_per_beat=ticks_per_beat,
        tempo_microseconds_per_beat=tempo,
        time_signature=time_signature,
        elements=tuple(
            StyleElement(
                type=element_type,
                name=element_type.value.replace("_", " ").title(),
                chord_variations=tuple(
                    sorted(
                        by_element[element_type],
                        key=lambda variation: variation.number or 0,
                    )
                ),
            )
            for element_type in _ELEMENT_ORDER
            if element_type in by_element
        ),
        metadata={
            "midi_format": 0,
            "midi_channel_numbering": "zero_based",
            "midi_program_numbering": "zero_based",
            "origin_authentication": "not_authenticated_by_file_format",
            "format_profile": "official_korg_pa80_style_to_midi_1.06",
            "source_chord_status": "not_present_in_smf",
            "source_style_tempo_status": "not_authenticated_by_export",
            "track_role_basis": "official_korg_style_channel_table",
            **({"library_group": group} if group is not None else {}),
        },
    )
    return Pa80StyleImportResult(
        style,
        Pa80StyleDiagnostics(
            ticks_per_beat=ticks_per_beat,
            time_signature=time_signature,
            declared_tempos=declared_tempos,
            files=tuple(
                sorted(
                    diagnostics,
                    key=lambda diagnostic: (
                        _ELEMENT_ORDER.index(diagnostic.element_type),
                        diagnostic.chord_variation,
                    ),
                )
            ),
        ),
    )


def pa80_diagnostics_to_dict(
    diagnostics: Pa80StyleDiagnostics,
) -> dict[str, JsonValue]:
    """Serialize Pa80 utility-export diagnostics."""

    return {
        "ticks_per_beat": diagnostics.ticks_per_beat,
        "time_signature": list(diagnostics.time_signature),
        "declared_tempos": list(diagnostics.declared_tempos),
        "files": [
            {
                "filename": item.filename,
                "element": item.element_type.value,
                "chord_variation": item.chord_variation,
                "length_ticks": item.length_ticks,
                "channels": list(item.channels),
                "message_counts": item.message_counts,
            }
            for item in diagnostics.files
        ],
    }


def _read_variation(
    path: Path, descriptor: tuple[StyleElementType, int]
) -> _VariationFile:
    try:
        with path.open("rb") as source:
            if source.read(4) != b"MThd":
                raise UnsupportedKorgStyleFormat(
                    f"Pa80 Chord Variation is not an SMF: {path.name}"
                )
        midi = mido.MidiFile(path)
    except UnsupportedKorgStyleFormat:
        raise
    except (OSError, EOFError, ValueError) as error:
        raise UnsupportedKorgStyleFormat(
            f"could not read Pa80 Chord Variation {path.name}: {error}"
        ) from error
    if int(midi.type) != 0 or len(midi.tracks) != 1:
        raise UnsupportedKorgStyleFormat(
            f"Pa80 Chord Variation must be a one-track format-0 SMF: {path.name}"
        )
    if int(midi.ticks_per_beat) <= 0:
        raise UnsupportedKorgStyleFormat(
            f"Pa80 Chord Variation uses SMPTE timing: {path.name}"
        )

    tick = 0
    messages: list[tuple[int, Any]] = []
    for message in midi.tracks[0]:
        tick += int(message.time)
        messages.append((tick, message))
    channel_messages = [
        message for _, message in messages if hasattr(message, "channel")
    ]
    unsupported = sorted(
        {
            str(message.type)
            for message in channel_messages
            if message.type not in _SUPPORTED_CHANNEL_MESSAGES
        }
    )
    if unsupported:
        raise UnsupportedKorgStyleFormat(
            f"unsupported Pa80 channel event(s) in {path.name}: "
            + ", ".join(unsupported)
        )
    channels = {int(message.channel) for message in channel_messages}
    unexpected_channels = sorted(channels - _CHANNEL_ROLES.keys())
    if unexpected_channels:
        one_based = ", ".join(str(channel + 1) for channel in unexpected_channels)
        raise UnsupportedKorgStyleFormat(
            f"unexpected Pa80 style MIDI channel(s) in {path.name}: {one_based}"
        )
    if not channels:
        raise UnsupportedKorgStyleFormat(
            f"Pa80 Chord Variation contains no channel events: {path.name}"
        )

    meters = [
        (int(message.numerator), int(message.denominator))
        for message_tick, message in messages
        if message_tick == 0 and message.type == "time_signature"
    ]
    if len(meters) != 1:
        raise UnsupportedKorgStyleFormat(
            f"Pa80 Chord Variation must declare one time signature at tick 0: "
            f"{path.name}"
        )
    tempos = [
        int(message.tempo)
        for message_tick, message in messages
        if message_tick == 0 and message.type == "set_tempo"
    ]
    return _VariationFile(
        descriptor=descriptor,
        path=path,
        ticks_per_beat=int(midi.ticks_per_beat),
        time_signature=meters[0],
        tempo=tempos[0] if len(tempos) == 1 else None,
        length_ticks=tick,
        messages=tuple(messages),
    )


def _channel_track(variation: _VariationFile, channel: int) -> StyleTrack:
    role = _CHANNEL_ROLES[channel]
    messages = [
        (tick, message)
        for tick, message in variation.messages
        if hasattr(message, "channel") and int(message.channel) == channel
    ]
    events: list[StyleEvent] = []
    active_notes: dict[int, list[tuple[int, int]]] = defaultdict(list)
    clipped_notes = 0
    for tick, message in messages:
        if (
            tick < variation.length_ticks
            and message.type == "note_on"
            and int(message.velocity) > 0
        ):
            active_notes[int(message.note)].append((tick, int(message.velocity)))
        elif message.type == "note_off" or (
            message.type == "note_on" and int(message.velocity) == 0
        ):
            note = int(message.note)
            if active_notes[note]:
                note_start, velocity = active_notes[note].pop(0)
                events.append(
                    NoteEvent(
                        start_tick=note_start,
                        duration_ticks=max(0, tick - note_start),
                        note=note,
                        velocity=velocity,
                        channel=channel,
                    )
                )
        elif tick < variation.length_ticks and message.type == "control_change":
            events.append(
                ControlChangeEvent(
                    tick=tick,
                    controller=int(message.control),
                    value=int(message.value),
                    channel=channel,
                )
            )
        elif tick < variation.length_ticks and message.type == "program_change":
            events.append(
                ProgramChangeEvent(
                    tick=tick,
                    program=int(message.program),
                    channel=channel,
                )
            )
        elif tick < variation.length_ticks and message.type == "pitchwheel":
            events.append(
                PitchBendEvent(
                    tick=tick,
                    pitch=int(message.pitch),
                    channel=channel,
                )
            )
    for note, starts in active_notes.items():
        for note_start, velocity in starts:
            clipped_notes += 1
            events.append(
                NoteEvent(
                    start_tick=note_start,
                    duration_ticks=max(0, variation.length_ticks - note_start),
                    note=note,
                    velocity=velocity,
                    channel=channel,
                )
            )
    events.sort(key=_event_sort_key)
    program = next(
        (
            event.program
            for event in events
            if isinstance(event, ProgramChangeEvent) and event.tick == 0
        ),
        None,
    )
    bank_msb = _initial_controller(events, 0)
    bank_lsb = _initial_controller(events, 32)
    return StyleTrack(
        role=role,
        source_name=_ROLE_NAMES[role],
        midi_channel=channel,
        program=program,
        bank_msb=bank_msb,
        bank_lsb=bank_lsb,
        events=tuple(events),
        metadata={
            "source_midi_file": variation.path.name,
            "midi_channel_one_based": channel + 1,
            "clipped_note_count": clipped_notes,
        },
    )


def _initial_controller(events: list[StyleEvent], controller: int) -> int | None:
    return next(
        (
            event.value
            for event in events
            if isinstance(event, ControlChangeEvent)
            and event.tick == 0
            and event.controller == controller
        ),
        None,
    )


def _event_sort_key(event: StyleEvent) -> tuple[int, str]:
    tick = event.start_tick if isinstance(event, NoteEvent) else event.tick
    return tick, type(event).__name__


def _descriptor_from_filename(
    filename: str,
) -> tuple[StyleElementType, int] | None:
    match = _VARIATION_FILENAME.fullmatch(filename)
    if match is not None:
        return (
            StyleElementType(f"variation_{match.group('element')}"),
            int(match.group("cv")),
        )
    match = _OTHER_FILENAME.fullmatch(filename)
    if match is None:
        return None
    prefix = {"i": "intro", "f": "fill", "e": "ending"}[match.group("prefix")]
    return (
        StyleElementType(f"{prefix}_{match.group('element')}"),
        int(match.group("cv")),
    )


def _style_id(name: str) -> str:
    identifier = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return f"korg-{identifier or 'imported-style'}"
