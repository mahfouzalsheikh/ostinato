from __future__ import annotations

import io
import json
import unittest

from ostinato.domain import ChordQuality
from ostinato.keyboard_input import (
    QUALITY_KEYS,
    ROOT_KEYS,
    KeyboardChordInput,
    KeyboardEventKind,
    run_keyboard,
)


class KeyboardChordInputTests(unittest.TestCase):
    def test_every_documented_root_key_emits_the_expected_pitch_class(self) -> None:
        controller = KeyboardChordInput(clock=lambda: 100)

        for key, pitch_class in ROOT_KEYS.items():
            with self.subTest(key=key):
                event = controller.handle_key(key)
                self.assertEqual(event.kind, KeyboardEventKind.CHORD)
                self.assertIsNotNone(event.chord)
                assert event.chord is not None
                self.assertEqual(event.chord.root_pitch_class, pitch_class)
                self.assertEqual(event.chord.recognized_at_ns, 100)

    def test_quality_change_re_emits_the_current_root(self) -> None:
        controller = KeyboardChordInput(clock=lambda: 100)
        controller.handle_key("g")

        event = controller.handle_key("x")

        self.assertEqual(event.kind, KeyboardEventKind.CHORD)
        self.assertIsNotNone(event.chord)
        assert event.chord is not None
        self.assertEqual(event.chord.name, "Gm")
        self.assertEqual(event.chord.quality, ChordQuality.MINOR)

    def test_quality_can_be_selected_before_a_root(self) -> None:
        controller = KeyboardChordInput()

        quality_event = controller.handle_key("v")
        chord_event = controller.handle_key("s")

        self.assertEqual(quality_event.kind, KeyboardEventKind.QUALITY)
        self.assertIsNotNone(chord_event.chord)
        assert chord_event.chord is not None
        self.assertEqual(chord_event.chord.name, "Ddim")

    def test_all_quality_keys_are_reachable(self) -> None:
        controller = KeyboardChordInput()

        observed = set()
        for key in QUALITY_KEYS:
            controller.handle_key(key)
            observed.add(controller.quality)

        self.assertEqual(observed, set(ChordQuality))

    def test_clear_panic_help_quit_and_unknown_are_explicit(self) -> None:
        controller = KeyboardChordInput()
        expected = {
            " ": KeyboardEventKind.CLEAR,
            "p": KeyboardEventKind.PANIC,
            "?": KeyboardEventKind.HELP,
            "q": KeyboardEventKind.QUIT,
            "!": KeyboardEventKind.UNKNOWN,
        }

        for key, kind in expected.items():
            with self.subTest(key=key):
                self.assertEqual(controller.handle_key(key).kind, kind)

    def test_tempo_controls_change_speed_in_five_bpm_steps(self) -> None:
        controller = KeyboardChordInput(tempo_bpm=120)

        slower = controller.handle_key("-")
        faster = controller.handle_key("+")
        unshifted_faster = controller.handle_key("=")

        self.assertEqual(slower.kind, KeyboardEventKind.TEMPO)
        self.assertEqual(slower.tempo_bpm, 115)
        self.assertEqual(faster.tempo_bpm, 120)
        self.assertEqual(unshifted_faster.tempo_bpm, 125)
        self.assertEqual(controller.tempo_bpm, 125)

    def test_tempo_controls_stop_at_safe_demo_limits(self) -> None:
        minimum = KeyboardChordInput(tempo_bpm=40)
        maximum = KeyboardChordInput(tempo_bpm=240)

        self.assertEqual(minimum.handle_key("-").tempo_bpm, 40)
        self.assertEqual(maximum.handle_key("+").tempo_bpm, 240)

    def test_scripted_json_mode_is_deterministic_in_structure(self) -> None:
        output = io.StringIO()

        exit_code = run_keyboard(keys="zagq", json_output=True, output_stream=output)
        events = [json.loads(line) for line in output.getvalue().splitlines()]

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            [event["kind"] for event in events], ["quality", "chord", "chord", "quit"]
        )
        self.assertEqual(events[1]["chord"]["name"], "C")
        self.assertEqual(events[2]["chord"]["name"], "G")

    def test_non_terminal_interactive_mode_has_actionable_error(self) -> None:
        output = io.StringIO()

        exit_code = run_keyboard(
            keys=None,
            json_output=False,
            input_stream=io.StringIO(),
            output_stream=output,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("--keys", output.getvalue())

    def test_event_handler_receives_each_scripted_event(self) -> None:
        observed: list[KeyboardEventKind] = []

        exit_code = run_keyboard(
            keys="zaq",
            json_output=False,
            output_stream=io.StringIO(),
            event_handler=lambda event: observed.append(event.kind),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            observed,
            [
                KeyboardEventKind.QUALITY,
                KeyboardEventKind.CHORD,
                KeyboardEventKind.QUIT,
            ],
        )


if __name__ == "__main__":
    unittest.main()
