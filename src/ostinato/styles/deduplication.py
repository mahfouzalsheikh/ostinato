"""Exact musical-payload fingerprints for the bounded imported-style policy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields

from ostinato.styles.live_audio import REQUIRED_SECTIONS
from ostinato.styles.models import Style, StyleEvent


def live_style_fingerprint(style: Style) -> str:
    """Hash only data that can affect the five live CV1 sections."""

    sections: list[object] = []
    for name, element_type in REQUIRED_SECTIONS.items():
        element = next(item for item in style.elements if item.type is element_type)
        variation = next(item for item in element.chord_variations if item.number == 1)
        sections.append(
            {
                "name": name,
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
                    for track in variation.tracks
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
