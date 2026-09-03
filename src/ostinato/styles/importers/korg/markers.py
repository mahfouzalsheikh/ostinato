"""Conservative normalization of KORG style MIDI labels."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ostinato.styles.models import StyleElementType, StyleTrackRole

_SECTION_MARKER = re.compile(
    r"(?P<section>variation|var|v|intro|i|fill|ending|end|e)"
    r"\s*[-_:]?\s*(?P<number>[1-4])"
    r"(?:\s*[-_:]?\s*(?:chord\s*variation|cv)\s*[-_:]?\s*(?P<cv>\d+))?",
    re.IGNORECASE,
)
_BREAK_MARKER = re.compile(
    r"(?:break|brk)"
    r"(?:\s*[-_:]?\s*(?:chord\s*variation|cv)\s*[-_:]?\s*(?P<cv>\d+))?",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class StyleElementDescriptor:
    """Normalized meaning of one explicitly recognized source marker."""

    element_type: StyleElementType
    chord_variation: int | None
    raw_marker: str


def normalize_korg_marker(marker: str) -> StyleElementDescriptor | None:
    """Normalize documented section vocabulary without guessing unknown labels."""

    cleaned = unicodedata.normalize("NFKC", marker).strip()
    break_match = _BREAK_MARKER.fullmatch(cleaned)
    if break_match is not None:
        return StyleElementDescriptor(
            StyleElementType.BREAK,
            _optional_positive_int(break_match.group("cv")),
            marker,
        )

    match = _SECTION_MARKER.fullmatch(cleaned)
    if match is None:
        return None
    section = match.group("section").lower()
    prefix = {
        "variation": "variation",
        "var": "variation",
        "v": "variation",
        "intro": "intro",
        "i": "intro",
        "fill": "fill",
        "ending": "ending",
        "end": "ending",
        "e": "ending",
    }[section]
    value = f"{prefix}_{match.group('number')}"
    try:
        element_type = StyleElementType(value)
    except ValueError:
        return None
    return StyleElementDescriptor(
        element_type,
        _optional_positive_int(match.group("cv")),
        marker,
    )


def normalize_korg_track_role(name: str) -> StyleTrackRole:
    """Infer a role only when a MIDI track carries an explicit role label."""

    compact = re.sub(r"[^a-z0-9]", "", name.casefold())
    direct = {
        "drum": StyleTrackRole.DRUM,
        "drums": StyleTrackRole.DRUM,
        "perc": StyleTrackRole.PERCUSSION,
        "percussion": StyleTrackRole.PERCUSSION,
        "bass": StyleTrackRole.BASS,
    }
    if compact in direct:
        return direct[compact]
    match = re.fullmatch(r"(?:acc|accompaniment)([1-5])", compact)
    if match is None:
        return StyleTrackRole.UNKNOWN
    return StyleTrackRole(f"acc{match.group(1)}")


def _optional_positive_int(value: str | None) -> int | None:
    if value is None:
        return None
    number = int(value)
    return number if number > 0 else None
