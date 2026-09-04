"""Learned MIDI fingerprints for hands-free arranger section control."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

PerformanceControlAction = Literal[
    "intro",
    "fill_1",
    "fill_2",
    "ending",
    "start",
    "stop",
    "variation_1",
    "variation_2",
    "variation_3",
    "variation_4",
    "intro_1",
    "intro_2",
    "ending_1",
    "ending_2",
]
PERFORMANCE_CONTROL_ACTIONS: tuple[PerformanceControlAction, ...] = (
    "intro",
    "fill_1",
    "fill_2",
    "ending",
    "start",
    "stop",
    "variation_1",
    "variation_2",
    "variation_3",
    "variation_4",
    "intro_1",
    "intro_2",
    "ending_1",
    "ending_2",
)
MAX_MESSAGES_PER_BINDING = 8
CONTROL_SEQUENCE_WINDOW_NS = 400_000_000
CONTROL_COOLDOWN_NS = 180_000_000

MidiFingerprint = tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PerformanceControlBinding:
    """One action and the exact observed MIDI message sequence that triggers it."""

    action: PerformanceControlAction
    messages: tuple[MidiFingerprint, ...]


def is_learnable_control_message(data: Sequence[int]) -> bool:
    """Return whether one validated MIDI message is safe to learn as a switch.

    Musical note/pressure/pitch messages, bellows expression, timing clock, and
    active sensing are intentionally excluded. They describe performance or
    connection state rather than a discrete arranger-control request.
    """

    if not data:
        return False
    status = data[0]
    family = status & 0xF0
    if family in {0x80, 0x90, 0xA0, 0xD0, 0xE0}:
        return False
    if family == 0xB0:
        return len(data) == 3 and data[1] != 11
    if family == 0xC0:
        return len(data) == 2
    return status not in {0xF8, 0xFE}


def performance_control_bindings(
    profile: Mapping[str, object] | None,
) -> tuple[PerformanceControlBinding, ...]:
    """Read already-validated bindings defensively from a saved profile."""

    if profile is None:
        return ()
    controls = profile.get("performance_controls")
    if not isinstance(controls, Mapping):
        return ()
    raw_bindings = controls.get("bindings")
    if not isinstance(raw_bindings, list):
        return ()

    bindings: list[PerformanceControlBinding] = []
    for raw_binding in raw_bindings:
        if not isinstance(raw_binding, Mapping):
            continue
        action = raw_binding.get("action")
        raw_messages = raw_binding.get("messages")
        if action not in PERFORMANCE_CONTROL_ACTIONS or not isinstance(
            raw_messages, list
        ):
            continue
        messages: list[MidiFingerprint] = []
        for raw_message in raw_messages:
            if not isinstance(raw_message, list) or not raw_message:
                messages = []
                break
            if any(
                type(byte) is not int or not 0 <= byte <= 255 for byte in raw_message
            ):
                messages = []
                break
            message = tuple(cast(int, byte) for byte in raw_message)
            if not is_learnable_control_message(message):
                messages = []
                break
            messages.append(message)
        if not 1 <= len(messages) <= MAX_MESSAGES_PER_BINDING:
            continue
        bindings.append(
            PerformanceControlBinding(
                cast(PerformanceControlAction, action), tuple(messages)
            )
        )
    return tuple(bindings)


class PerformanceControlRouter:
    """Match bounded recent MIDI sequences to explicitly learned actions."""

    def __init__(
        self,
        dispatch: Callable[[PerformanceControlAction], object],
        *,
        sequence_window_ns: int = CONTROL_SEQUENCE_WINDOW_NS,
        cooldown_ns: int = CONTROL_COOLDOWN_NS,
    ) -> None:
        if sequence_window_ns <= 0:
            raise ValueError("sequence_window_ns must be positive")
        if cooldown_ns < 0:
            raise ValueError("cooldown_ns cannot be negative")
        self._dispatch = dispatch
        self._sequence_window_ns = sequence_window_ns
        self._cooldown_ns = cooldown_ns
        self._input_port: str | None = None
        self._bindings: tuple[PerformanceControlBinding, ...] = ()
        self._recent: deque[tuple[int, MidiFingerprint]] = deque(
            maxlen=MAX_MESSAGES_PER_BINDING
        )
        self._last_trigger_ns: dict[PerformanceControlAction, int] = {}
        self._suspensions: set[object] = set()

    def configure_profile(self, profile: Mapping[str, object] | None) -> None:
        """Apply only bindings stored with the exact saved input profile."""

        input_port = profile.get("input_port") if profile is not None else None
        self._input_port = input_port if isinstance(input_port, str) else None
        self._bindings = tuple(
            sorted(
                performance_control_bindings(profile),
                key=lambda binding: len(binding.messages),
                reverse=True,
            )
        )
        self._recent.clear()
        self._last_trigger_ns.clear()

    def suspend(self, owner: object) -> None:
        """Suspend dispatch while one connected client is learning controls."""

        self._suspensions.add(owner)
        self._recent.clear()

    def resume(self, owner: object) -> None:
        """Release one client's learning suspension."""

        self._suspensions.discard(owner)
        self._recent.clear()

    def handle_midi_event(
        self, event: Mapping[str, object]
    ) -> PerformanceControlAction | None:
        """Dispatch and return an action when an observed fingerprint matches."""

        if self._suspensions or not self._bindings or self._input_port is None:
            return None
        if event.get("direction") != "in" or event.get("port") != self._input_port:
            return None
        timestamp_ns = event.get("timestamp_ns")
        raw_bytes = event.get("bytes")
        if type(timestamp_ns) is not int or not isinstance(raw_bytes, list):
            return None
        if any(type(byte) is not int or not 0 <= byte <= 255 for byte in raw_bytes):
            return None
        message = tuple(cast(int, byte) for byte in raw_bytes)
        if not is_learnable_control_message(message):
            return None

        timestamp = timestamp_ns
        while (
            self._recent and timestamp - self._recent[0][0] > self._sequence_window_ns
        ):
            self._recent.popleft()
        self._recent.append((timestamp, message))
        recent_messages = tuple(item[1] for item in self._recent)
        for binding in self._bindings:
            message_count = len(binding.messages)
            if recent_messages[-message_count:] != binding.messages:
                continue
            previous = self._last_trigger_ns.get(binding.action)
            self._recent.clear()
            if previous is not None and timestamp - previous < self._cooldown_ns:
                return None
            self._last_trigger_ns[binding.action] = timestamp
            self._dispatch(binding.action)
            return binding.action
        return None
