from __future__ import annotations

import unittest

from ostinato.performance_controls import (
    PerformanceControlRouter,
    is_learnable_control_message,
    performance_control_bindings,
)


def profile(*bindings: dict[str, object]) -> dict[str, object]:
    return {
        "input_port": "Accordion input",
        "performance_controls": {"bindings": list(bindings)},
    }


def event(data: list[int], timestamp_ns: int = 0) -> dict[str, object]:
    return {
        "direction": "in",
        "port": "Accordion input",
        "timestamp_ns": timestamp_ns,
        "bytes": data,
    }


class PerformanceControlBindingTests(unittest.TestCase):
    def test_only_discrete_non_performance_messages_are_learnable(self) -> None:
        self.assertTrue(is_learnable_control_message([0xFA]))
        self.assertTrue(is_learnable_control_message([0xFC]))
        self.assertTrue(is_learnable_control_message([0xB0, 64, 127]))
        self.assertTrue(is_learnable_control_message([0xC0, 3]))
        self.assertTrue(is_learnable_control_message([0xF0, 1, 2, 0xF7]))
        self.assertFalse(is_learnable_control_message([0x90, 60, 100]))
        self.assertFalse(is_learnable_control_message([0xB0, 11, 80]))
        self.assertFalse(is_learnable_control_message([0xF8]))
        self.assertFalse(is_learnable_control_message([0xFE]))

    def test_profile_parser_ignores_unvalidated_or_musical_bindings(self) -> None:
        parsed = performance_control_bindings(
            profile(
                {"action": "intro", "messages": [[0xFA]]},
                {"action": "unknown", "messages": [[0xFC]]},
                {"action": "fill_1", "messages": [[0x90, 60, 100]]},
            )
        )

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].action, "intro")
        self.assertEqual(parsed[0].messages, ((0xFA,),))


class PerformanceControlRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.actions: list[str] = []
        self.router = PerformanceControlRouter(
            self.actions.append,
            cooldown_ns=100,
            sequence_window_ns=1_000,
        )

    def test_single_message_dispatch_requires_saved_input_port(self) -> None:
        self.router.configure_profile(
            profile({"action": "intro", "messages": [[0xFA]]})
        )

        self.assertIsNone(
            self.router.handle_midi_event({**event([0xFA]), "port": "Another input"})
        )
        self.assertEqual(self.router.handle_midi_event(event([0xFA])), "intro")
        self.assertEqual(self.actions, ["intro"])

    def test_multi_message_fingerprint_ignores_bellows_and_note_traffic(self) -> None:
        self.router.configure_profile(
            profile(
                {
                    "action": "ending",
                    "messages": [[0xB0, 0, 1], [0xC0, 7]],
                }
            )
        )

        self.router.handle_midi_event(event([0xB0, 0, 1], 0))
        self.router.handle_midi_event(event([0xB0, 11, 50], 10))
        self.router.handle_midi_event(event([0x90, 60, 100], 20))
        result = self.router.handle_midi_event(event([0xC0, 7], 30))

        self.assertEqual(result, "ending")
        self.assertEqual(self.actions, ["ending"])

    def test_expired_sequence_and_action_cooldown_do_not_dispatch(self) -> None:
        self.router.configure_profile(
            profile(
                {
                    "action": "fill_1",
                    "messages": [[0xB0, 64, 127], [0xB0, 64, 0]],
                }
            )
        )

        self.router.handle_midi_event(event([0xB0, 64, 127], 0))
        self.assertIsNone(self.router.handle_midi_event(event([0xB0, 64, 0], 1_001)))
        self.router.handle_midi_event(event([0xB0, 64, 127], 2_000))
        self.assertEqual(
            self.router.handle_midi_event(event([0xB0, 64, 0], 2_010)),
            "fill_1",
        )
        self.router.handle_midi_event(event([0xB0, 64, 127], 2_020))
        self.assertIsNone(self.router.handle_midi_event(event([0xB0, 64, 0], 2_030)))
        self.assertEqual(self.actions, ["fill_1"])

    def test_learning_suspension_is_owned_and_clears_partial_sequences(self) -> None:
        first_owner = object()
        second_owner = object()
        self.router.configure_profile(profile({"action": "stop", "messages": [[0xFC]]}))

        self.router.suspend(first_owner)
        self.router.suspend(second_owner)
        self.assertIsNone(self.router.handle_midi_event(event([0xFC])))
        self.router.resume(first_owner)
        self.assertIsNone(self.router.handle_midi_event(event([0xFC], 200)))
        self.router.resume(second_owner)
        self.assertEqual(self.router.handle_midi_event(event([0xFC], 400)), "stop")


if __name__ == "__main__":
    unittest.main()
