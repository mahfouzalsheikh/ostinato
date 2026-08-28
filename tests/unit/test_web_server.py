from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from ostinato.realtime_midi import MidiService
from ostinato.web_server import create_app
from tests.fake_midi import FakeMidiBackend


class WebServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = FakeMidiBackend()
        self.service = MidiService(self.backend, poll_interval_seconds=0.01)
        self.client_context = TestClient(create_app(self.service))
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)

    def test_health_and_surface_assets_are_served(self) -> None:
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})
        index = self.client.get("/")
        component = self.client.get("/assets/fr4x-accordion.js")

        self.assertEqual(index.status_code, 200)
        self.assertIn("<fr4x-accordion", index.text)
        self.assertEqual(component.status_code, 200)
        self.assertIn("PIANO_KEY_COUNT = 37", component.text)
        self.assertIn("BASS_ROW_COUNT = 6", component.text)
        self.assertIn("BASS_COLUMN_COUNT = 20", component.text)

    def test_ports_are_selected_only_by_an_available_exact_name(self) -> None:
        selected = self.client.put(
            "/api/midi/ports",
            json={
                "input": "Accordion test input",
                "output": "Synth test output",
            },
        )
        invented = self.client.put(
            "/api/midi/ports",
            json={"input": "FR-4X invented default", "output": None},
        )

        self.assertEqual(selected.status_code, 200)
        self.assertIs(selected.json()["input_connected"], True)
        self.assertEqual(invented.status_code, 409)
        self.assertIn("not available", invented.json()["detail"])

    def test_http_midi_send_uses_selected_fake_output(self) -> None:
        self.client.put(
            "/api/midi/ports",
            json={"input": None, "output": "Synth test output"},
        )
        response = self.client.post(
            "/api/midi/send",
            json={"bytes": [0x90, 72, 110]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["direction"], "out")
        self.assertEqual(self.backend.output_handles[-1].sent, [(0x90, 72, 110)])

    def test_http_midi_send_does_not_coerce_non_integer_bytes(self) -> None:
        response = self.client.post(
            "/api/midi/send",
            json={"bytes": ["144", 72, 110]},
        )

        self.assertEqual(response.status_code, 422)

    def test_websocket_receives_status_and_rejects_unknown_command(self) -> None:
        with self.client.websocket_connect("/ws/midi") as socket:
            status = socket.receive_json()
            socket.send_json({"type": "unsupported"})
            error = socket.receive_json()

        self.assertEqual(status["type"], "status")
        self.assertEqual(error["type"], "error")
        self.assertIn("unknown command", error["message"])

    def test_websocket_disconnect_releases_started_note(self) -> None:
        self.client.put(
            "/api/midi/ports",
            json={"input": None, "output": "Synth test output"},
        )
        output = self.backend.output_handles[-1]
        with self.client.websocket_connect("/ws/midi") as socket:
            socket.receive_json()
            socket.send_json({"type": "midi.send", "bytes": [0x92, 70, 88]})
            event = socket.receive_json()

        self.assertEqual(event["message_type"], "note_on")
        self.assertEqual(output.sent, [(0x92, 70, 88), (0x82, 70, 0)])


if __name__ == "__main__":
    unittest.main()
