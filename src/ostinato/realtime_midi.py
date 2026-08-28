"""Hardware-independent real-time MIDI service for the web interface.

The service deliberately deals in raw MIDI bytes and user-selected port names.
It does not assign FR-4X channels or interpret left-hand button semantics.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable, Sequence
from typing import Any, Protocol, cast

import mido  # type: ignore[import-untyped]

MidiBytes = tuple[int, ...]
MidiCallback = Callable[[MidiBytes], None]
JsonObject = dict[str, object]


class MidiServiceError(RuntimeError):
    """Base error surfaced safely through the HTTP/WebSocket boundary."""


class PortSelectionError(MidiServiceError):
    """A requested MIDI port does not currently exist."""


class MidiOutputUnavailable(MidiServiceError):
    """No selected MIDI output is currently connected."""


class InvalidMidiMessage(MidiServiceError):
    """A browser supplied malformed MIDI bytes."""


class CloseablePort(Protocol):
    """The close operation shared by MIDI input and output handles."""

    def close(self) -> None:
        """Release the underlying port."""


class OutputPort(CloseablePort, Protocol):
    """Output handle used by :class:`MidiService`."""

    def send(self, data: MidiBytes) -> None:
        """Send one complete MIDI message."""


class MidiBackend(Protocol):
    """Injectable MIDI backend so tests never require hardware."""

    def input_names(self) -> tuple[str, ...]:
        """Return currently available input names."""

    def output_names(self) -> tuple[str, ...]:
        """Return currently available output names."""

    def open_input(self, name: str, callback: MidiCallback) -> CloseablePort:
        """Open ``name`` and deliver complete messages to ``callback``."""

    def open_output(self, name: str) -> OutputPort:
        """Open ``name`` for message output."""


class _MidoInput:
    def __init__(self, port: Any) -> None:
        self._port = port

    def close(self) -> None:
        self._port.close()


class _MidoOutput:
    def __init__(self, port: Any) -> None:
        self._port = port

    def close(self) -> None:
        self._port.close()

    def send(self, data: MidiBytes) -> None:
        self._port.send(mido.Message.from_bytes(list(data)))


class MidoBackend:
    """Production backend using mido and python-rtmidi/ALSA."""

    def input_names(self) -> tuple[str, ...]:
        return tuple(sorted(cast(list[str], mido.get_input_names())))

    def output_names(self) -> tuple[str, ...]:
        return tuple(sorted(cast(list[str], mido.get_output_names())))

    def open_input(self, name: str, callback: MidiCallback) -> CloseablePort:
        def on_message(message: Any) -> None:
            callback(tuple(cast(list[int], message.bytes())))

        return _MidoInput(mido.open_input(name, callback=on_message))

    def open_output(self, name: str) -> OutputPort:
        return _MidoOutput(mido.open_output(name))


def validate_midi_bytes(values: Sequence[object]) -> MidiBytes:
    """Validate one complete MIDI message and return immutable bytes."""

    if not values:
        raise InvalidMidiMessage("a MIDI message cannot be empty")
    if len(values) > 1024:
        raise InvalidMidiMessage("a MIDI message cannot exceed 1024 bytes")
    if any(type(value) is not int or not 0 <= value <= 255 for value in values):
        raise InvalidMidiMessage("MIDI bytes must be integers from 0 through 255")

    data = tuple(cast(int, value) for value in values)
    try:
        mido.Message.from_bytes(list(data))
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidMidiMessage(f"invalid MIDI message: {error}") from error
    return data


_CHANNEL_TYPES = {
    0x80: "note_off",
    0x90: "note_on",
    0xA0: "polytouch",
    0xB0: "control_change",
    0xC0: "program_change",
    0xD0: "aftertouch",
    0xE0: "pitchwheel",
}


def describe_midi_message(
    data: MidiBytes,
    *,
    direction: str,
    port: str,
    timestamp_ns: int,
) -> JsonObject:
    """Build a browser-safe event without adding instrument semantics."""

    status = data[0]
    family = status & 0xF0
    event: JsonObject = {
        "type": "midi",
        "direction": direction,
        "port": port,
        "timestamp_ns": timestamp_ns,
        "bytes": list(data),
        "message_type": _CHANNEL_TYPES.get(family, "system"),
        "channel": (status & 0x0F) + 1 if family in _CHANNEL_TYPES else None,
    }
    if family in (0x80, 0x90, 0xA0) and len(data) == 3:
        event["note"] = data[1]
        event["velocity"] = data[2]
    elif family == 0xB0 and len(data) == 3:
        event["control"] = data[1]
        event["value"] = data[2]
    elif family == 0xC0 and len(data) == 2:
        event["program"] = data[1]
    return event


class MidiService:
    """Own selected ports and fan raw events out to WebSocket subscribers."""

    def __init__(
        self,
        backend: MidiBackend | None = None,
        *,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._backend = backend or MidoBackend()
        self._poll_interval_seconds = poll_interval_seconds
        self._input_name: str | None = None
        self._output_name: str | None = None
        self._input: CloseablePort | None = None
        self._output: OutputPort | None = None
        self._subscribers: set[asyncio.Queue[JsonObject]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._monitor: asyncio.Task[None] | None = None
        self._error: str | None = None
        self._anonymous_owner = object()
        self._active_notes: dict[object, set[tuple[int, int]]] = {}

    async def start(self) -> None:
        """Attach to the active event loop and begin reconnect monitoring."""

        if self._monitor is not None:
            return
        self._loop = asyncio.get_running_loop()
        self._monitor = asyncio.create_task(
            self._monitor_ports(), name="ostinato-midi-monitor"
        )

    async def stop(self) -> None:
        """Close ports and stop the reconnect monitor."""

        monitor = self._monitor
        self._monitor = None
        if monitor is not None:
            monitor.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await monitor
        self._close_input()
        self._close_output()
        self._loop = None

    def subscribe(self) -> asyncio.Queue[JsonObject]:
        """Create a bounded event queue for one browser."""

        queue: asyncio.Queue[JsonObject] = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[JsonObject]) -> None:
        """Remove a browser queue."""

        self._subscribers.discard(queue)

    def snapshot(self) -> JsonObject:
        """Return selected and currently available ports."""

        try:
            inputs = list(self._backend.input_names())
            outputs = list(self._backend.output_names())
        except Exception as error:  # backend errors are diagnostics, not crashes
            inputs = []
            outputs = []
            self._error = f"MIDI discovery failed: {error}"
        return {
            "type": "status",
            "inputs": inputs,
            "outputs": outputs,
            "selected_input": self._input_name,
            "selected_output": self._output_name,
            "input_connected": self._input is not None,
            "output_connected": self._output is not None,
            "error": self._error,
        }

    def select_ports(
        self,
        *,
        input_name: str | None,
        output_name: str | None,
    ) -> JsonObject:
        """Select exact names reported by discovery; ``None`` disconnects."""

        inputs = self._backend.input_names()
        outputs = self._backend.output_names()
        if input_name is not None and input_name not in inputs:
            raise PortSelectionError(f"MIDI input is not available: {input_name}")
        if output_name is not None and output_name not in outputs:
            raise PortSelectionError(f"MIDI output is not available: {output_name}")

        self._close_input()
        self._close_output()
        self._input_name = input_name
        self._output_name = output_name
        self._error = None
        self._open_selected_ports(inputs=inputs, outputs=outputs)
        snapshot = self.snapshot()
        self._publish(snapshot)
        return snapshot

    def send(
        self,
        values: Sequence[object],
        *,
        owner: object | None = None,
    ) -> JsonObject:
        """Validate and send one message through the selected output."""

        data = validate_midi_bytes(values)
        output = self._output
        if output is None or self._output_name is None:
            raise MidiOutputUnavailable("select a connected MIDI output first")
        try:
            output.send(data)
        except Exception as error:
            self._close_output()
            self._error = f"MIDI output failed: {error}"
            self._publish(self.snapshot())
            raise MidiOutputUnavailable(self._error) from error

        event = describe_midi_message(
            data,
            direction="out",
            port=self._output_name,
            timestamp_ns=time.monotonic_ns(),
        )
        note_owner = self._anonymous_owner if owner is None else owner
        self._track_note(data, owner=note_owner)
        self._publish(event)
        return event

    def release(self, owner: object) -> None:
        """Release every note started by one WebSocket client."""

        notes = self._active_notes.pop(owner, set())
        remaining = (
            set().union(*self._active_notes.values()) if self._active_notes else set()
        )
        self._release_notes(notes - remaining)

    async def _monitor_ports(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval_seconds)
            before = (
                self._input is not None,
                self._output is not None,
                self._error,
            )
            try:
                inputs = self._backend.input_names()
                outputs = self._backend.output_names()
                if self._input is not None and self._input_name not in inputs:
                    self._close_input()
                if self._output is not None and self._output_name not in outputs:
                    self._close_output()
                self._open_selected_ports(inputs=inputs, outputs=outputs)
            except Exception as error:
                self._error = f"MIDI reconnect failed: {error}"
            after = (
                self._input is not None,
                self._output is not None,
                self._error,
            )
            if after != before:
                self._publish(self.snapshot())

    def _open_selected_ports(
        self,
        *,
        inputs: tuple[str, ...],
        outputs: tuple[str, ...],
    ) -> None:
        errors: list[str] = []
        if (
            self._input is None
            and self._input_name is not None
            and self._input_name in inputs
        ):
            source = self._input_name
            try:
                self._input = self._backend.open_input(
                    source,
                    lambda data: self._receive_from_thread(source, data),
                )
            except Exception as error:
                errors.append(f"MIDI input failed: {error}")
        if (
            self._output is None
            and self._output_name is not None
            and self._output_name in outputs
        ):
            try:
                self._output = self._backend.open_output(self._output_name)
            except Exception as error:
                errors.append(f"MIDI output failed: {error}")
        self._error = "; ".join(errors) or None

    def _receive_from_thread(self, source: str, data: MidiBytes) -> None:
        event = describe_midi_message(
            data,
            direction="in",
            port=source,
            timestamp_ns=time.monotonic_ns(),
        )
        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(self._publish, event)

    def _publish(self, event: JsonObject) -> None:
        for queue in tuple(self._subscribers):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(event)

    def _close_input(self) -> None:
        if self._input is not None:
            with contextlib.suppress(Exception):
                self._input.close()
        self._input = None

    def _close_output(self) -> None:
        if self._output is not None:
            notes = (
                set().union(*self._active_notes.values())
                if self._active_notes
                else set()
            )
            self._active_notes.clear()
            self._release_notes(notes)
            with contextlib.suppress(Exception):
                self._output.close()
        self._output = None

    def _track_note(self, data: MidiBytes, *, owner: object) -> None:
        family = data[0] & 0xF0
        if family not in (0x80, 0x90) or len(data) != 3:
            return
        signature = ((data[0] & 0x0F) + 1, data[1])
        notes = self._active_notes.setdefault(owner, set())
        if family == 0x90 and data[2] > 0:
            notes.add(signature)
        else:
            notes.discard(signature)
        if not notes:
            self._active_notes.pop(owner, None)

    def _release_notes(self, notes: set[tuple[int, int]]) -> None:
        output = self._output
        port = self._output_name
        if output is None or port is None:
            return
        for channel, note in sorted(notes):
            data = (0x80 | (channel - 1), note, 0)
            with contextlib.suppress(Exception):
                output.send(data)
                self._publish(
                    describe_midi_message(
                        data,
                        direction="out",
                        port=port,
                        timestamp_ns=time.monotonic_ns(),
                    )
                )
