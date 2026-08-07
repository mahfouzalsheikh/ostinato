"""Shared musical domain types.

These types are input-source independent. An FR-4X mapper may produce them only
after hardware captures establish its MIDI semantics; the keyboard simulator
produces them directly from explicit user choices.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class ChordQuality(StrEnum):
    """Chord qualities supported by the computer-keyboard simulator."""

    MAJOR = "major"
    MINOR = "minor"
    DOMINANT_SEVENTH = "dominant_seventh"
    DIMINISHED = "diminished"


PITCH_CLASS_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")


@dataclass(frozen=True, slots=True)
class ChordState:
    """Normalized harmony understood by the future arranger engine."""

    root_pitch_class: int
    quality: ChordQuality
    bass_pitch_class: int | None
    confidence: float
    source_event_ids: tuple[str, ...]
    recognized_at_ns: int

    def __post_init__(self) -> None:
        if not 0 <= self.root_pitch_class <= 11:
            raise ValueError("root_pitch_class must be between 0 and 11")
        if self.bass_pitch_class is not None and not 0 <= self.bass_pitch_class <= 11:
            raise ValueError("bass_pitch_class must be between 0 and 11")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if self.recognized_at_ns < 0:
            raise ValueError("recognized_at_ns cannot be negative")

    @property
    def name(self) -> str:
        """Return a compact, human-readable chord name."""

        suffix = {
            ChordQuality.MAJOR: "",
            ChordQuality.MINOR: "m",
            ChordQuality.DOMINANT_SEVENTH: "7",
            ChordQuality.DIMINISHED: "dim",
        }[self.quality]
        return f"{PITCH_CLASS_NAMES[self.root_pitch_class]}{suffix}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize the state for diagnostics and scripted tests."""

        result = asdict(self)
        result["quality"] = self.quality.value
        result["name"] = self.name
        return result
