"""Computer-keyboard chord input for hardware-free testing."""

from __future__ import annotations

import json
import sys
import termios
import time
import tty
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TextIO

from ostinato.domain import ChordQuality, ChordState

ROOT_KEYS: dict[str, int] = {
    "a": 0,
    "w": 1,
    "s": 2,
    "e": 3,
    "d": 4,
    "f": 5,
    "t": 6,
    "g": 7,
    "y": 8,
    "h": 9,
    "u": 10,
    "j": 11,
}

QUALITY_KEYS: dict[str, ChordQuality] = {
    "z": ChordQuality.MAJOR,
    "x": ChordQuality.MINOR,
    "c": ChordQuality.DOMINANT_SEVENTH,
    "v": ChordQuality.DIMINISHED,
}


class KeyboardEventKind(StrEnum):
    """Kinds of event emitted by the keyboard simulator."""

    CHORD = "chord"
    QUALITY = "quality"
    CLEAR = "clear"
    PANIC = "panic"
    HELP = "help"
    QUIT = "quit"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class KeyboardEvent:
    """One explicit computer-keyboard input event."""

    kind: KeyboardEventKind
    key: str
    detail: str
    chord: ChordState | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize an event for scripted testing."""

        return {
            "kind": self.kind.value,
            "key": self.key,
            "detail": self.detail,
            "chord": self.chord.to_dict() if self.chord else None,
        }


class KeyboardChordInput:
    """Stateful mapping from documented keys to normalized chord states."""

    def __init__(self, *, clock: Callable[[], int] = time.monotonic_ns) -> None:
        self._clock = clock
        self._quality = ChordQuality.MAJOR
        self._root_pitch_class: int | None = None
        self._event_number = 0

    @property
    def quality(self) -> ChordQuality:
        return self._quality

    def handle_key(self, key: str) -> KeyboardEvent:
        """Translate one key without reading the terminal or emitting MIDI."""

        if len(key) != 1:
            raise ValueError("keyboard input must contain exactly one character")
        normalized = key.casefold()

        if normalized in ROOT_KEYS:
            self._root_pitch_class = ROOT_KEYS[normalized]
            return self._chord_event(normalized)

        if normalized in QUALITY_KEYS:
            self._quality = QUALITY_KEYS[normalized]
            if self._root_pitch_class is not None:
                return self._chord_event(normalized)
            return KeyboardEvent(
                KeyboardEventKind.QUALITY,
                normalized,
                f"quality set to {self._quality.value}; choose a root",
            )

        if key == " ":
            self._root_pitch_class = None
            return KeyboardEvent(
                KeyboardEventKind.CLEAR,
                "space",
                "simulated chord cleared",
            )
        if normalized == "p":
            return KeyboardEvent(
                KeyboardEventKind.PANIC,
                normalized,
                "panic requested; no MIDI sink is attached in this simulator",
            )
        if normalized == "?":
            return KeyboardEvent(KeyboardEventKind.HELP, normalized, "show controls")
        if normalized == "q":
            return KeyboardEvent(KeyboardEventKind.QUIT, normalized, "quit requested")
        return KeyboardEvent(
            KeyboardEventKind.UNKNOWN,
            normalized,
            f"unmapped key {key!r}",
        )

    def _chord_event(self, key: str) -> KeyboardEvent:
        root = self._root_pitch_class
        if root is None:
            raise RuntimeError("a chord event requires a selected root")
        self._event_number += 1
        chord = ChordState(
            root_pitch_class=root,
            quality=self._quality,
            bass_pitch_class=None,
            confidence=1.0,
            source_event_ids=(f"computer-keyboard-{self._event_number}",),
            recognized_at_ns=self._clock(),
        )
        return KeyboardEvent(
            KeyboardEventKind.CHORD,
            key,
            f"chord changed to {chord.name}",
            chord,
        )


def controls_text() -> str:
    """Return the keyboard layout shown in the terminal and documentation."""

    roots = "  roots:     a=C w=C# s=D e=Eb d=E f=F t=F# g=G y=Ab h=A u=Bb j=B"
    qualities = "  qualities: z=major x=minor c=dominant-7 v=diminished"
    commands = "  commands:  space=clear p=panic ?=help q=quit"
    return "\n".join((roots, qualities, commands))


def render_event(event: KeyboardEvent, *, json_output: bool) -> str:
    """Render one event for a human or a test harness."""

    if json_output:
        return json.dumps(event.to_dict(), sort_keys=True)
    return f"{event.kind.value.upper():<7} {event.detail}"


@contextmanager
def _terminal_keys(stream: TextIO) -> Iterator[Iterator[str]]:
    if not stream.isatty():
        raise RuntimeError("interactive keyboard mode requires a terminal")
    descriptor = stream.fileno()
    original = termios.tcgetattr(descriptor)
    try:
        tty.setcbreak(descriptor)

        def read_keys() -> Iterator[str]:
            while value := stream.read(1):
                yield value

        yield read_keys()
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, original)


def run_keyboard(
    *,
    keys: str | None,
    json_output: bool,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> int:
    """Run scripted or interactive computer-keyboard chord input."""

    controller = KeyboardChordInput()
    if keys is not None:
        return _process_keys(iter(keys), controller, json_output, output_stream)

    print("Ostinato computer-keyboard chord input", file=output_stream)
    print(controls_text(), file=output_stream)
    print(
        "This changes chord state only; accompaniment audio is not implemented.",
        file=output_stream,
    )
    try:
        with _terminal_keys(input_stream) as key_iterator:
            return _process_keys(key_iterator, controller, json_output, output_stream)
    except RuntimeError as error:
        print(f"ERROR: {error}", file=output_stream)
        print("Use --keys for non-interactive testing.", file=output_stream)
        return 2
    except KeyboardInterrupt:
        print("\nQUIT    interrupted", file=output_stream)
        return 130


def _process_keys(
    keys: Iterator[str],
    controller: KeyboardChordInput,
    json_output: bool,
    output_stream: TextIO,
) -> int:
    for key in keys:
        event = controller.handle_key(key)
        if event.kind is KeyboardEventKind.HELP and not json_output:
            print(controls_text(), file=output_stream)
        else:
            print(render_event(event, json_output=json_output), file=output_stream)
        if event.kind is KeyboardEventKind.QUIT:
            return 0
    return 0
