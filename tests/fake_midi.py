"""Hardware-free MIDI backend shared by web and service tests."""

from __future__ import annotations

from ostinato.realtime_midi import MidiBytes, MidiCallback


class FakeInput:
    def __init__(self, callback: MidiCallback) -> None:
        self.callback = callback
        self.closed = False

    def emit(self, data: MidiBytes) -> None:
        self.callback(data)

    def close(self) -> None:
        self.closed = True


class FakeOutput:
    def __init__(self) -> None:
        self.sent: list[MidiBytes] = []
        self.closed = False

    def send(self, data: MidiBytes) -> None:
        self.sent.append(data)

    def close(self) -> None:
        self.closed = True


class FakeMidiBackend:
    def __init__(self) -> None:
        self.inputs: list[str] = ["Accordion test input"]
        self.outputs: list[str] = ["Synth test output"]
        self.input_handles: list[FakeInput] = []
        self.output_handles: list[FakeOutput] = []

    def input_names(self) -> tuple[str, ...]:
        return tuple(self.inputs)

    def output_names(self) -> tuple[str, ...]:
        return tuple(self.outputs)

    def open_input(self, name: str, callback: MidiCallback) -> FakeInput:
        if name not in self.inputs:
            raise RuntimeError("input disappeared")
        handle = FakeInput(callback)
        self.input_handles.append(handle)
        return handle

    def open_output(self, name: str) -> FakeOutput:
        if name not in self.outputs:
            raise RuntimeError("output disappeared")
        handle = FakeOutput()
        self.output_handles.append(handle)
        return handle
