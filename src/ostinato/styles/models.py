"""Vendor-neutral data model for offline-imported arranger styles."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, cast

type JsonValue = (
    bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
)


class StyleElementType(StrEnum):
    """Musical sections supported by the arranger import boundary."""

    INTRO_1 = "intro_1"
    INTRO_2 = "intro_2"
    INTRO_3 = "intro_3"
    VARIATION_1 = "variation_1"
    VARIATION_2 = "variation_2"
    VARIATION_3 = "variation_3"
    VARIATION_4 = "variation_4"
    FILL_1 = "fill_1"
    FILL_2 = "fill_2"
    FILL_3 = "fill_3"
    FILL_4 = "fill_4"
    BREAK = "break"
    ENDING_1 = "ending_1"
    ENDING_2 = "ending_2"
    ENDING_3 = "ending_3"


class StyleTrackRole(StrEnum):
    """Playback role, inferred only from explicit source metadata."""

    DRUM = "drum"
    PERCUSSION = "percussion"
    BASS = "bass"
    ACC1 = "acc1"
    ACC2 = "acc2"
    ACC3 = "acc3"
    ACC4 = "acc4"
    ACC5 = "acc5"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class NoteEvent:
    """One note in ticks relative to the start of its chord variation."""

    start_tick: int
    duration_ticks: int
    note: int
    velocity: int
    channel: int


@dataclass(frozen=True, slots=True)
class ControlChangeEvent:
    """A MIDI controller change relative to the chord variation."""

    tick: int
    controller: int
    value: int
    channel: int


@dataclass(frozen=True, slots=True)
class ProgramChangeEvent:
    """A MIDI program change relative to the chord variation."""

    tick: int
    program: int
    channel: int


@dataclass(frozen=True, slots=True)
class PitchBendEvent:
    """A MIDI pitch-wheel change relative to the chord variation."""

    tick: int
    pitch: int
    channel: int


type StyleEvent = NoteEvent | ControlChangeEvent | ProgramChangeEvent | PitchBendEvent


@dataclass(frozen=True, slots=True)
class StyleTrack:
    """Events and preserved MIDI voice metadata for one accompaniment track."""

    role: StyleTrackRole
    source_name: str
    midi_channel: int | None
    program: int | None
    bank_msb: int | None
    bank_lsb: int | None
    events: tuple[StyleEvent, ...]
    metadata: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChordVariation:
    """A distinct source chord variation within one style element."""

    number: int | None
    source_chord: str | None
    length_ticks: int
    tracks: tuple[StyleTrack, ...]
    metadata: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StyleElement:
    """An intro, variation, fill, break, or ending."""

    type: StyleElementType
    name: str
    chord_variations: tuple[ChordVariation, ...]
    metadata: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StyleSource:
    """Provenance retained without coupling playback to a vendor format."""

    manufacturer: str
    source_format: str
    original_file: str
    package: str | None = None


@dataclass(frozen=True, slots=True)
class Style:
    """Complete vendor-neutral style imported from an offline source."""

    version: int
    id: str
    name: str
    source: StyleSource
    ticks_per_beat: int
    tempo_microseconds_per_beat: int | None
    time_signature: tuple[int, int] | None
    elements: tuple[StyleElement, ...]
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    @property
    def tempo_bpm(self) -> float | None:
        """Return display BPM while retaining exact integer MIDI tempo."""

        if self.tempo_microseconds_per_beat is None:
            return None
        return 60_000_000 / self.tempo_microseconds_per_beat


def style_to_dict(style: Style) -> dict[str, JsonValue]:
    """Serialize a style into the readable version-1 JSON representation."""

    return {
        "version": style.version,
        "id": style.id,
        "name": style.name,
        "source": {
            "manufacturer": style.source.manufacturer,
            "source_format": style.source.source_format,
            "original_file": style.source.original_file,
            "package": style.source.package,
        },
        "ticks_per_beat": style.ticks_per_beat,
        "tempo_microseconds_per_beat": style.tempo_microseconds_per_beat,
        "tempo_bpm": style.tempo_bpm,
        "time_signature": (
            list(style.time_signature) if style.time_signature is not None else None
        ),
        "elements": [_element_to_dict(element) for element in style.elements],
        "metadata": style.metadata,
    }


class StyleDocumentError(ValueError):
    """A persisted vendor-neutral style document is malformed."""


def style_from_dict(value: object) -> Style:
    """Validate and deserialize a version-1 style document."""

    document = _mapping(value, "style")
    version = _integer(document, "version", minimum=1, maximum=1)
    source_value = _mapping(document.get("source"), "style.source")
    signature_value = document.get("time_signature")
    time_signature: tuple[int, int] | None = None
    if signature_value is not None:
        if not isinstance(signature_value, list) or len(signature_value) != 2:
            raise StyleDocumentError("style.time_signature must contain two integers")
        numerator = _bounded_integer(
            signature_value[0], "time signature numerator", 1, 32
        )
        denominator = _bounded_integer(
            signature_value[1], "time signature denominator", 1, 32
        )
        time_signature = (numerator, denominator)
    elements_value = document.get("elements")
    if not isinstance(elements_value, list) or not elements_value:
        raise StyleDocumentError("style.elements must be a non-empty list")
    return Style(
        version=version,
        id=_text(document, "id"),
        name=_text(document, "name"),
        source=StyleSource(
            manufacturer=_text(source_value, "manufacturer"),
            source_format=_text(source_value, "source_format"),
            original_file=_text(source_value, "original_file"),
            package=_optional_text(source_value, "package"),
        ),
        ticks_per_beat=_integer(document, "ticks_per_beat", minimum=1),
        tempo_microseconds_per_beat=_optional_integer(
            document, "tempo_microseconds_per_beat", minimum=1
        ),
        time_signature=time_signature,
        elements=tuple(
            _element_from_dict(item, f"style.elements[{index}]")
            for index, item in enumerate(elements_value)
        ),
        metadata=_metadata(document, "metadata"),
    )


def _element_from_dict(value: object, path: str) -> StyleElement:
    document = _mapping(value, path)
    variations_value = document.get("chord_variations")
    if not isinstance(variations_value, list) or not variations_value:
        raise StyleDocumentError(f"{path}.chord_variations must be a non-empty list")
    try:
        element_type = StyleElementType(_text(document, "type"))
    except ValueError as error:
        raise StyleDocumentError(f"{path}.type is not supported") from error
    return StyleElement(
        type=element_type,
        name=_text(document, "name"),
        chord_variations=tuple(
            _variation_from_dict(item, f"{path}.chord_variations[{index}]")
            for index, item in enumerate(variations_value)
        ),
        metadata=_metadata(document, "metadata"),
    )


def _variation_from_dict(value: object, path: str) -> ChordVariation:
    document = _mapping(value, path)
    tracks_value = document.get("tracks")
    if not isinstance(tracks_value, list) or not tracks_value:
        raise StyleDocumentError(f"{path}.tracks must be a non-empty list")
    return ChordVariation(
        number=_optional_integer(document, "number", minimum=1),
        source_chord=_optional_text(document, "source_chord"),
        length_ticks=_integer(document, "length_ticks", minimum=1),
        tracks=tuple(
            _track_from_dict(item, f"{path}.tracks[{index}]")
            for index, item in enumerate(tracks_value)
        ),
        metadata=_metadata(document, "metadata"),
    )


def _track_from_dict(value: object, path: str) -> StyleTrack:
    document = _mapping(value, path)
    events_value = document.get("events")
    if not isinstance(events_value, list):
        raise StyleDocumentError(f"{path}.events must be a list")
    try:
        role = StyleTrackRole(_text(document, "role"))
    except ValueError as error:
        raise StyleDocumentError(f"{path}.role is not supported") from error
    return StyleTrack(
        role=role,
        source_name=_text(document, "source_name"),
        midi_channel=_optional_integer(document, "midi_channel", minimum=0, maximum=15),
        program=_optional_integer(document, "program", minimum=0, maximum=127),
        bank_msb=_optional_integer(document, "bank_msb", minimum=0, maximum=127),
        bank_lsb=_optional_integer(document, "bank_lsb", minimum=0, maximum=127),
        events=tuple(
            _event_from_dict(item, f"{path}.events[{index}]")
            for index, item in enumerate(events_value)
        ),
        metadata=_metadata(document, "metadata"),
    )


def _event_from_dict(value: object, path: str) -> StyleEvent:
    document = _mapping(value, path)
    event_type = _text(document, "type")
    channel = _integer(document, "channel", minimum=0, maximum=15)
    if event_type == "note":
        return NoteEvent(
            start_tick=_integer(document, "start_tick", minimum=0),
            duration_ticks=_integer(document, "duration_ticks", minimum=0),
            note=_integer(document, "note", minimum=0, maximum=127),
            velocity=_integer(document, "velocity", minimum=1, maximum=127),
            channel=channel,
        )
    if event_type == "control_change":
        return ControlChangeEvent(
            tick=_integer(document, "tick", minimum=0),
            controller=_integer(document, "controller", minimum=0, maximum=127),
            value=_integer(document, "value", minimum=0, maximum=127),
            channel=channel,
        )
    if event_type == "program_change":
        return ProgramChangeEvent(
            tick=_integer(document, "tick", minimum=0),
            program=_integer(document, "program", minimum=0, maximum=127),
            channel=channel,
        )
    if event_type == "pitch_bend":
        return PitchBendEvent(
            tick=_integer(document, "tick", minimum=0),
            pitch=_integer(document, "pitch", minimum=-8192, maximum=8191),
            channel=channel,
        )
    raise StyleDocumentError(f"{path}.type is not supported")


def _mapping(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise StyleDocumentError(f"{path} must be an object")
    return cast(dict[str, Any], value)


def _text(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise StyleDocumentError(f"{key} must be non-empty text")
    return result


def _optional_text(value: dict[str, Any], key: str) -> str | None:
    result = value.get(key)
    if result is None:
        return None
    if not isinstance(result, str) or not result.strip():
        raise StyleDocumentError(f"{key} must be non-empty text or null")
    return result


def _integer(
    value: dict[str, Any], key: str, *, minimum: int, maximum: int | None = None
) -> int:
    return _bounded_integer(value.get(key), key, minimum, maximum)


def _optional_integer(
    value: dict[str, Any], key: str, *, minimum: int, maximum: int | None = None
) -> int | None:
    result = value.get(key)
    if result is None:
        return None
    return _bounded_integer(result, key, minimum, maximum)


def _bounded_integer(
    value: object, label: str, minimum: int, maximum: int | None = None
) -> int:
    if (
        type(value) is not int
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        bounds = f"{minimum}..{maximum}" if maximum is not None else f">= {minimum}"
        raise StyleDocumentError(f"{label} must be an integer in {bounds}")
    return value


def _metadata(value: dict[str, Any], key: str) -> dict[str, JsonValue]:
    result = value.get(key, {})
    if not isinstance(result, dict) or not all(
        isinstance(item, str) for item in result
    ):
        raise StyleDocumentError(f"{key} must be an object")
    return cast(dict[str, JsonValue], result)


def _element_to_dict(element: StyleElement) -> dict[str, JsonValue]:
    return {
        "type": element.type.value,
        "name": element.name,
        "chord_variations": [
            {
                "number": variation.number,
                "source_chord": variation.source_chord,
                "length_ticks": variation.length_ticks,
                "tracks": [_track_to_dict(track) for track in variation.tracks],
                "metadata": variation.metadata,
            }
            for variation in element.chord_variations
        ],
        "metadata": element.metadata,
    }


def _track_to_dict(track: StyleTrack) -> dict[str, JsonValue]:
    return {
        "role": track.role.value,
        "source_name": track.source_name,
        "midi_channel": track.midi_channel,
        "program": track.program,
        "bank_msb": track.bank_msb,
        "bank_lsb": track.bank_lsb,
        "events": [_event_to_dict(event) for event in track.events],
        "metadata": track.metadata,
    }


def _event_to_dict(event: StyleEvent) -> dict[str, JsonValue]:
    if isinstance(event, NoteEvent):
        return {
            "type": "note",
            "start_tick": event.start_tick,
            "duration_ticks": event.duration_ticks,
            "note": event.note,
            "velocity": event.velocity,
            "channel": event.channel,
        }
    if isinstance(event, ControlChangeEvent):
        return {
            "type": "control_change",
            "tick": event.tick,
            "controller": event.controller,
            "value": event.value,
            "channel": event.channel,
        }
    if isinstance(event, ProgramChangeEvent):
        return {
            "type": "program_change",
            "tick": event.tick,
            "program": event.program,
            "channel": event.channel,
        }
    return {
        "type": "pitch_bend",
        "tick": event.tick,
        "pitch": event.pitch,
        "channel": event.channel,
    }
