"""Guided, observation-only MIDI role detection."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypedDict

MidiRole = Literal["treble", "bass", "chord"]
MIDI_ROLES: tuple[MidiRole, ...] = ("treble", "bass", "chord")


class MidiDetectionError(ValueError):
    """The guided observations are not sufficient for role detection."""


@dataclass(frozen=True)
class NoteObservation:
    """One note-on observed during a user-labeled wizard phase."""

    channel: int
    note: int


class ChannelCandidate(TypedDict):
    """Ranked activity observed on one channel."""

    channel: int
    event_count: int
    notes: list[int]
    confidence: float


class RoleDetection(TypedDict):
    """Detection result for one user-labeled physical role."""

    primary_channel: int
    candidates: list[ChannelCandidate]
    note_min: int
    note_max: int
    event_count: int
    confidence: float


def detect_midi_roles(
    captures: Mapping[MidiRole, Sequence[NoteObservation]],
) -> dict[MidiRole, RoleDetection]:
    """Rank channels for each role without assuming an instrument mapping.

    Activity observed in the selected role increases the score. Activity on the
    same channel during the other guided phases reduces confidence, making a
    shared or ambiguous channel visible for human review.
    """

    counts_by_role: dict[MidiRole, Counter[int]] = {}
    notes_by_role: dict[MidiRole, dict[int, set[int]]] = {}
    totals: Counter[int] = Counter()

    for role in MIDI_ROLES:
        observations = captures.get(role, ())
        if not observations:
            raise MidiDetectionError(f"no note activity was captured for {role}")
        counts = Counter(observation.channel for observation in observations)
        notes: dict[int, set[int]] = defaultdict(set)
        for observation in observations:
            notes[observation.channel].add(observation.note)
        counts_by_role[role] = counts
        notes_by_role[role] = dict(notes)
        totals.update(counts)

    detections: dict[MidiRole, RoleDetection] = {}
    for role in MIDI_ROLES:
        candidates: list[ChannelCandidate] = []
        for channel, event_count in counts_by_role[role].items():
            exclusivity = event_count / totals[channel]
            coverage = min(1.0, event_count / 8)
            confidence = round((exclusivity * 0.75) + (coverage * 0.25), 3)
            candidates.append(
                {
                    "channel": channel,
                    "event_count": event_count,
                    "notes": sorted(notes_by_role[role][channel]),
                    "confidence": confidence,
                }
            )
        candidates.sort(
            key=lambda item: (
                -item["confidence"],
                -item["event_count"],
                item["channel"],
            )
        )
        primary = candidates[0]
        primary_notes = primary["notes"]
        detections[role] = {
            "primary_channel": primary["channel"],
            "candidates": candidates,
            "note_min": min(primary_notes),
            "note_max": max(primary_notes),
            "event_count": primary["event_count"],
            "confidence": primary["confidence"],
        }

    return detections
