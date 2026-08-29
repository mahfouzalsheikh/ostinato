"""Guided, expiring evidence for FR-4X accompaniment output routing."""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

ARRANGER_PARTS = ("bass", "chord", "drum")
PROBE_TTL_NS = 30 * 60 * 1_000_000_000

# Documented FR-4X defaults. The UI presents them as probe starting points,
# never as detected or confirmed routing.
ROUTING_MODE_CHANNELS: dict[str, dict[str, int]] = {
    "native": {"bass": 2, "chord": 3, "drum": 10},
    "orchestral": {"bass": 5, "chord": 6, "drum": 10},
    "shared_orchestra": {"bass": 4, "chord": 4, "drum": 10},
}


class ArrangerProbeError(ValueError):
    """A probe confirmation is missing, expired, or does not match."""


@dataclass(frozen=True, slots=True)
class ProbeRecord:
    """One successfully dispatched bounded output probe."""

    part: str
    channel: int
    output_port: str
    issued_at_ns: int


def routing_mode_catalog() -> list[dict[str, object]]:
    """Return documented starting points with their explicit semantics."""

    return [
        {
            "id": "native",
            "name": "Native Bass & Chord",
            "description": "FR-4X Bass/Free Bass and Chord parts",
            "channels": dict(ROUTING_MODE_CHANNELS["native"]),
        },
        {
            "id": "orchestral",
            "name": "Orchestra Bass & Chord",
            "description": "FR-4X Orchestra Bass and Orchestra Chord parts",
            "channels": dict(ROUTING_MODE_CHANNELS["orchestral"]),
        },
        {
            "id": "shared_orchestra",
            "name": "Shared Orchestra Part",
            "description": "One FR-4X Orchestra/Organ part for Bass and Chord",
            "channels": dict(ROUTING_MODE_CHANNELS["shared_orchestra"]),
        },
    ]


class ArrangerProbeRegistry:
    """Issue and validate short-lived proof that exact probes were dispatched."""

    def __init__(self, *, clock: Callable[[], int] = time.monotonic_ns) -> None:
        self._clock = clock
        self._records: dict[str, ProbeRecord] = {}

    def issue(self, *, part: str, channel: int, output_port: str) -> str:
        """Record one completed probe and return its opaque confirmation token."""

        if part not in ARRANGER_PARTS:
            raise ArrangerProbeError(f"unknown arranger part: {part}")
        if not 1 <= channel <= 16:
            raise ArrangerProbeError("probe channel must be from 1 through 16")
        if not output_port:
            raise ArrangerProbeError("a connected MIDI output is required")
        self._purge_expired()
        token = secrets.token_urlsafe(24)
        self._records[token] = ProbeRecord(
            part=part,
            channel=channel,
            output_port=output_port,
            issued_at_ns=self._clock(),
        )
        return token

    def validate(
        self,
        *,
        tokens: Mapping[str, str],
        channels: Mapping[str, int],
        output_port: str,
    ) -> None:
        """Require one unexpired matching probe for every routed part."""

        self._purge_expired()
        if set(tokens) != set(ARRANGER_PARTS):
            raise ArrangerProbeError(
                "bass, chord, and drum probes must all be confirmed"
            )
        for part in ARRANGER_PARTS:
            record = self._records.get(tokens[part])
            if record is None:
                raise ArrangerProbeError(f"the {part} probe is missing or expired")
            if (
                record.part != part
                or record.channel != channels.get(part)
                or record.output_port != output_port
            ):
                raise ArrangerProbeError(
                    f"the {part} probe does not match the selected channel and output"
                )

    def consume(self, tokens: Mapping[str, str]) -> None:
        """Make saved probe evidence one-use so it cannot approve another route."""

        for token in tokens.values():
            self._records.pop(token, None)

    def _purge_expired(self) -> None:
        cutoff = self._clock() - PROBE_TTL_NS
        self._records = {
            token: record
            for token, record in self._records.items()
            if record.issued_at_ns >= cutoff
        }
