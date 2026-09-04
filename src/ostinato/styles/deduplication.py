"""Exact musical-payload fingerprints for the bounded imported-style policy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields

from ostinato.styles.models import Style, StyleEvent


def live_style_fingerprint(style: Style) -> str:
    """Hash every exported section and chord pattern, independent of identity."""

    sections: list[object] = []
    for element in sorted(style.elements, key=lambda item: item.type.value):
        for variation in sorted(
            element.chord_variations, key=lambda item: item.number or 0
        ):
            sections.append(
                {
                    "name": element.type.value,
                    "chord_variation": variation.number,
                    "source_chord": variation.source_chord,
                    "length_ticks": variation.length_ticks,
                    "tracks": [
                        {
                            "role": track.role.value,
                            "midi_channel": track.midi_channel,
                            "program": track.program,
                            "bank_msb": track.bank_msb,
                            "bank_lsb": track.bank_lsb,
                            "events": [_event_payload(event) for event in track.events],
                        }
                        for track in sorted(
                            variation.tracks,
                            key=lambda item: (item.role.value, item.midi_channel or 0),
                        )
                    ],
                }
            )
    payload = {
        "ticks_per_beat": style.ticks_per_beat,
        "time_signature": style.time_signature,
        "sections": sections,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def duplicate_live_style_groups(
    styles: tuple[Style, ...],
) -> tuple[tuple[Style, ...], ...]:
    """Return stable groups whose complete live musical payloads are identical."""

    grouped: dict[str, list[Style]] = {}
    for style in styles:
        grouped.setdefault(live_style_fingerprint(style), []).append(style)
    return tuple(tuple(items) for _, items in sorted(grouped.items()) if len(items) > 1)


def _event_payload(event: StyleEvent) -> dict[str, int | str]:
    return {
        "type": type(event).__name__,
        **{field.name: int(getattr(event, field.name)) for field in fields(event)},
    }
