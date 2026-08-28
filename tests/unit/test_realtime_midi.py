from __future__ import annotations

import asyncio
import unittest

from ostinato.realtime_midi import (
    InvalidMidiMessage,
    MidiOutputUnavailable,
    MidiService,
    PortSelectionError,
    describe_midi_message,
    validate_midi_bytes,
)
from tests.fake_midi import FakeMidiBackend


class MidiMessageTests(unittest.TestCase):
    def test_validate_accepts_complete_channel_message(self) -> None:
        self.assertEqual(validate_midi_bytes([0x90, 60, 100]), (0x90, 60, 100))

    def test_validate_rejects_invalid_byte_and_incomplete_message(self) -> None:
        with self.assertRaisesRegex(InvalidMidiMessage, "0 through 255"):
            validate_midi_bytes([0x90, 60, 300])
        with self.assertRaisesRegex(InvalidMidiMessage, "invalid MIDI message"):
            validate_midi_bytes([0x90, 60])

    def test_description_uses_one_based_channel_without_instrument_mapping(
        self,
    ) -> None:
        event = describe_midi_message(
            (0x92, 64, 87),
            direction="in",
            port="fixture",
            timestamp_ns=123,
        )

        self.assertEqual(event["message_type"], "note_on")
        self.assertEqual(event["channel"], 3)
        self.assertEqual(event["note"], 64)
        self.assertEqual(event["velocity"], 87)
        self.assertEqual(event["timestamp_ns"], 123)


class MidiServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.backend = FakeMidiBackend()
        self.service = MidiService(self.backend, poll_interval_seconds=0.01)
        await self.service.start()

    async def asyncTearDown(self) -> None:
        await self.service.stop()

    async def test_exact_port_selection_and_raw_input_fanout(self) -> None:
        queue = self.service.subscribe()
        snapshot = self.service.select_ports(
            input_name="Accordion test input",
            output_name="Synth test output",
        )
        await queue.get()  # selection status

        self.assertIs(snapshot["input_connected"], True)
        self.assertIs(snapshot["output_connected"], True)
        self.backend.input_handles[-1].emit((0x90, 60, 99))
        event = await asyncio.wait_for(queue.get(), timeout=0.2)

        self.assertEqual(event["direction"], "in")
        self.assertEqual(event["port"], "Accordion test input")
        self.assertEqual(event["bytes"], [0x90, 60, 99])

    async def test_browser_output_is_validated_sent_and_published(self) -> None:
        queue = self.service.subscribe()
        self.service.select_ports(input_name=None, output_name="Synth test output")
        await queue.get()

        event = self.service.send([0x81, 65, 0])
        published = await asyncio.wait_for(queue.get(), timeout=0.2)

        self.assertEqual(self.backend.output_handles[-1].sent, [(0x81, 65, 0)])
        self.assertEqual(event["direction"], "out")
        self.assertEqual(published, event)

    async def test_missing_or_unselected_output_fails_actionably(self) -> None:
        with self.assertRaisesRegex(MidiOutputUnavailable, "select"):
            self.service.send([0x90, 60, 100])
        with self.assertRaisesRegex(PortSelectionError, "not available"):
            self.service.select_ports(input_name="invented port", output_name=None)

    async def test_client_release_sends_note_off_for_its_active_notes(self) -> None:
        owner = object()
        self.service.select_ports(input_name=None, output_name="Synth test output")
        output = self.backend.output_handles[-1]

        self.service.send([0x94, 67, 91], owner=owner)
        self.service.release(owner)

        self.assertEqual(output.sent, [(0x94, 67, 91), (0x84, 67, 0)])

    async def test_client_release_does_not_stop_same_note_owned_by_peer(self) -> None:
        first_owner = object()
        second_owner = object()
        self.service.select_ports(input_name=None, output_name="Synth test output")
        output = self.backend.output_handles[-1]
        self.service.send([0x90, 60, 90], owner=first_owner)
        self.service.send([0x90, 60, 80], owner=second_owner)

        self.service.release(first_owner)
        self.assertEqual(output.sent, [(0x90, 60, 90), (0x90, 60, 80)])

        self.service.release(second_owner)
        self.assertEqual(output.sent[-1], (0x80, 60, 0))

    async def test_selected_port_reconnects_after_disappearing(self) -> None:
        self.service.select_ports(
            input_name="Accordion test input",
            output_name=None,
        )
        first = self.backend.input_handles[-1]
        self.backend.inputs.clear()
        await asyncio.sleep(0.03)

        self.assertTrue(first.closed)
        self.assertIs(self.service.snapshot()["input_connected"], False)

        self.backend.inputs.append("Accordion test input")
        await asyncio.sleep(0.03)

        self.assertGreaterEqual(len(self.backend.input_handles), 2)
        self.assertIs(self.service.snapshot()["input_connected"], True)


if __name__ == "__main__":
    unittest.main()
