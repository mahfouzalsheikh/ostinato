"""Shared, JSON-safe arrangement timelines for built-in and custom styles."""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from ostinato.computer_audio import DEMO_STYLES, DemoArrangementRenderer, DemoSection
from ostinato.sfz_audio import STYLE_SFZ_PROFILES
from ostinato.style_designer import INSTRUMENTS, CustomStyle
from ostinato.styles.live_audio import imported_style_playback_info
from ostinato.styles.models import NoteEvent, Style, StyleTrackRole


@dataclass(frozen=True, slots=True)
class LaneDefinition:
    """Display metadata and renderer level attribute for one musical role."""

    id: str
    label: str
    level_attribute: str
    duration_attribute: str | None


LANES = (
    LaneDefinition("bass", "Bass line", "bass", "_BASS_DURATION_BEATS"),
    LaneDefinition("comp", "Chord rhythm", "piano", "_CHORD_DURATION_BEATS"),
    LaneDefinition("fill", "Melodic answers", "bandoneon", "_REED_DURATION_BEATS"),
    LaneDefinition("backing", "Backing texture", "strings", "_PAD_DURATION_BEATS"),
    LaneDefinition("drums", "Drums & percussion", "drums", None),
)

INSTRUMENT_NAMES = {
    "upright_bass": "Upright bass",
    "electric_bass_finger": "Fingered electric bass",
    "electric_bass_pick": "Picked electric bass",
    "piano": "Acoustic grand piano",
    "acoustic_guitar": "Acoustic guitar",
    "electric_guitar": "Clean electric guitar",
    "flute": "Flute",
    "clarinet": "Clarinet",
    "trumpet": "Trumpet",
    "violin": "Violin",
    "cello": "Cello section",
    "drum_kit": "Studio drum kit",
    "brushed_drums": "Brush drum kit",
}


def _instrument_ids(style_id: str) -> dict[str, str]:
    if style_id == "classic_waltz":
        return {
            "bass": "upright_bass",
            "comp": "piano",
            "fill": "flute",
            "backing": "cello",
            "drums": "brushed_drums",
        }
    profile = STYLE_SFZ_PROFILES[style_id]
    return {
        "bass": profile.bass,
        "comp": profile.comp,
        "fill": profile.fill,
        "backing": profile.pad,
        "drums": profile.drums,
    }


def _accents(values: tuple[float, ...], count: int) -> tuple[float, ...]:
    return values if values else (1.0,) * count


def _events(
    starts: tuple[float, ...],
    accents: tuple[float, ...],
    *,
    bar_start: float,
    duration: float,
    dynamic: float,
    kind: str,
) -> list[dict[str, Any]]:
    return [
        {
            "start": round(bar_start + start, 3),
            "duration": round(max(0.08, duration), 3),
            "intensity": round(min(1.35, accent * dynamic) * 74),
            "kind": kind,
        }
        for start, accent in zip(starts, _accents(accents, len(starts)), strict=True)
    ]


def _lane_events(
    renderer: type[DemoArrangementRenderer],
    lane_id: str,
    *,
    phrase_bars: int,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    beats_per_bar = renderer.BEATS_PER_BAR
    dynamics = renderer._PHRASE_DYNAMICS
    for bar_index in range(phrase_bars):
        groove = renderer._groove_for_section(DemoSection.MAIN, bar_index)
        bar_start = bar_index * beats_per_bar
        dynamic = dynamics[bar_index % len(dynamics)]
        if lane_id == "bass":
            events.extend(
                _events(
                    groove.bass_onsets,
                    groove.bass_accents,
                    bar_start=bar_start,
                    duration=renderer._BASS_DURATION_BEATS,
                    dynamic=dynamic,
                    kind="bass",
                )
            )
        elif lane_id == "comp":
            events.extend(
                _events(
                    groove.chord_onsets,
                    groove.chord_accents,
                    bar_start=bar_start,
                    duration=renderer._CHORD_DURATION_BEATS,
                    dynamic=dynamic,
                    kind="chord",
                )
            )
        elif lane_id == "fill":
            starts = (
                groove.reed_onsets
                if groove.reed_onsets is not None
                else groove.chord_onsets
            )
            events.extend(
                _events(
                    starts,
                    groove.reed_accents,
                    bar_start=bar_start,
                    duration=renderer._REED_DURATION_BEATS,
                    dynamic=dynamic,
                    kind="answer",
                )
            )
        elif lane_id == "backing":
            starts = groove.pad_onsets if groove.pad_onsets is not None else (0.0,)
            duration = renderer._PAD_DURATION_BEATS
            if duration is None:
                duration = beats_per_bar - 0.05
            events.extend(
                _events(
                    starts,
                    (),
                    bar_start=bar_start,
                    duration=duration,
                    dynamic=dynamic,
                    kind="texture",
                )
            )
        else:
            drum_parts = (
                (groove.kick_onsets, groove.kick_accents, "kick"),
                (groove.snare_onsets, groove.snare_accents, "snare"),
                (groove.auxiliary_onsets, groove.auxiliary_accents, "percussion"),
                (
                    groove.hat_onsets
                    if groove.hat_onsets is not None
                    else tuple(
                        step * 0.5
                        for step in range(round(renderer.BEATS_PER_BAR / 0.5))
                    ),
                    groove.hat_accents,
                    "timekeeper",
                ),
            )
            for starts, accents, kind in drum_parts:
                events.extend(
                    _events(
                        starts,
                        accents,
                        bar_start=bar_start,
                        duration=0.16,
                        dynamic=dynamic,
                        kind=kind,
                    )
                )
    return sorted(events, key=lambda event: (float(event["start"]), str(event["kind"])))


def built_in_style_timeline(style_id: str) -> dict[str, Any]:
    """Describe the audible four-bar main phrase of a built-in style."""

    definition = DEMO_STYLES[style_id]
    renderer = definition.renderer
    phrase_bars = min(4, len(renderer._PHRASE_DYNAMICS))
    instruments = _instrument_ids(style_id)
    levels = renderer._MAIN_LEVELS
    maximum_dynamic = max(renderer._PHRASE_DYNAMICS[:phrase_bars])
    lanes: list[dict[str, Any]] = []
    for lane in LANES:
        lane_level = getattr(levels, lane.level_attribute)
        if lane.id == "drums":
            lane_level = max(levels.drums, levels.percussion)
        instrument_id = instruments[lane.id]
        lanes.append(
            {
                "id": lane.id,
                "label": lane.label,
                "instrument": INSTRUMENT_NAMES.get(
                    instrument_id, instrument_id.replace("_", " ").title()
                ),
                "level": round(min(1.0, lane_level) * 100),
                "events": _lane_events(
                    renderer,
                    lane.id,
                    phrase_bars=phrase_bars,
                ),
            }
        )
    return {
        "style_id": style_id,
        "name": definition.name,
        "beats_per_bar": definition.beats_per_bar,
        "phrase_bars": phrase_bars,
        "total_beats": phrase_bars * definition.beats_per_bar,
        "bar_dynamics": [
            round(dynamic / maximum_dynamic * 100)
            for dynamic in renderer._PHRASE_DYNAMICS[:phrase_bars]
        ],
        "lanes": lanes,
    }


def custom_style_timeline(style: CustomStyle) -> dict[str, Any]:
    """Apply a custom palette, gate, phrase length, and mix to its base groove."""

    timeline: dict[str, Any] = deepcopy(built_in_style_timeline(style.base_style_id))
    timeline.update(
        style_id=style.id,
        name=style.name,
        phrase_bars=style.phrase_bars,
        total_beats=style.phrase_bars * style.beats_per_bar,
    )
    timeline["bar_dynamics"] = timeline["bar_dynamics"][: style.phrase_bars]
    total_beats = style.phrase_bars * style.beats_per_bar
    for lane in timeline["lanes"]:
        lane_id = lane["id"]
        if lane_id == "drums":
            lane["instrument"] = "Studio drum kit" if style.drums_enabled else "Off"
            lane["level"] = style.drums_volume if style.drums_enabled else 0
            gate = 1.0
        else:
            settings = style.layer(lane_id)
            instrument = INSTRUMENTS[settings.instrument]
            lane["instrument"] = instrument.name
            lane["level"] = settings.volume if instrument.program is not None else 0
            gate = settings.gate_percent / 100
        lane["events"] = [
            {
                **event,
                "duration": round(float(event["duration"]) * gate, 3),
            }
            for event in lane["events"]
            if float(event["start"]) < total_beats
        ]
    return timeline


def imported_style_timeline(style: Style) -> dict[str, Any]:
    """Describe the exact Variation 1 CV1 material used by live playback."""

    info = imported_style_playback_info(style)
    variation = info.sections["main"]
    beats_per_bar = info.beats_per_bar
    total_beats = variation.length_ticks / style.ticks_per_beat
    phrase_bars = max(1, math.ceil(total_beats / beats_per_bar))
    roles = {
        "bass": {StyleTrackRole.BASS},
        "comp": {StyleTrackRole.ACC1, StyleTrackRole.ACC2},
        "fill": {StyleTrackRole.ACC3},
        "backing": {StyleTrackRole.ACC4, StyleTrackRole.ACC5},
        "drums": {StyleTrackRole.DRUM, StyleTrackRole.PERCUSSION},
    }
    lanes: list[dict[str, Any]] = []
    bar_velocities: list[list[int]] = [[] for _ in range(phrase_bars)]
    for lane in LANES:
        tracks = [track for track in variation.tracks if track.role in roles[lane.id]]
        notes = sorted(
            (
                event
                for track in tracks
                for event in track.events
                if isinstance(event, NoteEvent)
            ),
            key=lambda event: (event.start_tick, event.note),
        )
        for note in notes:
            bar = min(
                phrase_bars - 1,
                note.start_tick // (style.ticks_per_beat * beats_per_bar),
            )
            bar_velocities[bar].append(note.velocity)
        programs = sorted(
            {track.program for track in tracks if track.program is not None}
        )
        instrument = (
            "GM percussion approximation"
            if lane.id == "drums"
            else (
                "GM program " + ", ".join(str(program + 1) for program in programs)
                if programs
                else "Source role"
            )
        )
        lanes.append(
            {
                "id": lane.id,
                "label": lane.label,
                "instrument": instrument,
                "level": round(
                    sum(note.velocity for note in notes) / len(notes) / 127 * 100
                )
                if notes
                else 0,
                "events": [
                    {
                        "start": round(note.start_tick / style.ticks_per_beat, 3),
                        "duration": round(
                            note.duration_ticks / style.ticks_per_beat, 3
                        ),
                        "intensity": note.velocity,
                        "kind": lane.id,
                    }
                    for note in notes
                ],
            }
        )
    averages = [sum(values) / len(values) if values else 0 for values in bar_velocities]
    maximum = max(averages, default=0) or 1
    return {
        "style_id": style.id,
        "name": style.name,
        "beats_per_bar": beats_per_bar,
        "phrase_bars": phrase_bars,
        "total_beats": total_beats,
        "bar_dynamics": [round(value / maximum * 100) for value in averages],
        "lanes": lanes,
        "imported": True,
        "playback_policy": "Variation 1 CV1 · Ostinato chord adaptation",
    }
