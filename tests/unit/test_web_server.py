from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from ostinato.midi_profile import MidiProfileStore
from ostinato.realtime_midi import MidiService
from ostinato.web_server import create_app
from tests.fake_midi import FakeMidiBackend


class WebServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.backend = FakeMidiBackend()
        self.service = MidiService(self.backend, poll_interval_seconds=0.01)
        self.profile_store = MidiProfileStore(
            Path(self.temporary.name) / "midi-profile.json"
        )
        self.client_context = TestClient(create_app(self.service, self.profile_store))
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.temporary.cleanup()

    def test_health_and_surface_assets_are_served(self) -> None:
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})
        index = self.client.get("/")
        component = self.client.get("/assets/fr4x-accordion.js")
        surface_mapping = self.client.get("/assets/midi-surface.js")
        stradella = self.client.get("/assets/stradella.js")

        self.assertEqual(index.status_code, 200)
        self.assertIn("<fr4x-accordion", index.text)
        self.assertEqual(component.status_code, 200)
        self.assertEqual(surface_mapping.status_code, 200)
        self.assertEqual(stradella.status_code, 200)
        self.assertIn("PIANO_KEY_COUNT = 37", surface_mapping.text)
        self.assertIn("STRADELLA_ROW_COUNT = 6", stradella.text)
        self.assertIn("STRADELLA_COLUMN_COUNT = 20", stradella.text)
        self.assertIn("inferPianoBase", surface_mapping.text)
        self.assertIn("classifyChordNotes", stradella.text)
        self.assertIn("Stradella · 2 bass rows", component.text)
        self.assertNotIn('class="bellows"', component.text)
        self.assertNotIn("Explicit mapping", index.text)
        self.assertNotIn("User-trained bindings", index.text)
        self.assertIn('id="midi-wizard"', index.text)
        self.assertIn("Perform one labeled part at a time", index.text)

    def test_guided_detection_uses_only_submitted_observations(self) -> None:
        response = self.client.post(
            "/api/midi/detect",
            json={
                "treble": [
                    {"channel": 9, "note": note}
                    for note in (48, 52, 55, 60, 64, 67, 72, 84)
                ],
                "bass": [
                    {"channel": 3, "note": note}
                    for note in (36, 38, 40, 41, 43, 45, 47, 48)
                ],
                "chord": [
                    {"channel": 12, "note": note}
                    for note in (48, 52, 55, 59, 62, 65, 69, 71)
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        roles = response.json()["roles"]
        self.assertEqual(roles["treble"]["primary_channel"], 9)
        self.assertEqual(roles["bass"]["primary_channel"], 3)
        self.assertEqual(roles["chord"]["primary_channel"], 12)

    def test_profile_round_trip_and_clear(self) -> None:
        profile = self._profile_payload()

        self.assertIsNone(self.client.get("/api/midi/profile").json())
        saved = self.client.put("/api/midi/profile", json=profile)
        loaded = self.client.get("/api/midi/profile")

        self.assertEqual(saved.status_code, 200)
        self.assertIn("saved_at", saved.json())
        self.assertEqual(loaded.json(), saved.json())
        self.assertEqual(self.client.delete("/api/midi/profile").status_code, 204)
        self.assertIsNone(self.client.get("/api/midi/profile").json())

    def test_saved_profile_restores_exact_ports_during_service_startup(self) -> None:
        backend = FakeMidiBackend()
        service = MidiService(backend, poll_interval_seconds=0.01)
        store = MidiProfileStore(Path(self.temporary.name) / "startup-profile.json")
        store.save(self._profile_payload())

        with TestClient(create_app(service, store)) as client:
            status = client.get("/api/midi/status").json()

        self.assertEqual(status["selected_input"], "Accordion test input")
        self.assertEqual(status["selected_output"], "Synth test output")
        self.assertIs(status["input_connected"], True)
        self.assertIs(status["output_connected"], True)

    def test_profile_rejects_a_primary_channel_that_was_not_observed(self) -> None:
        profile = self._profile_payload()
        profile["roles"]["bass"]["primary_channel"] = 16

        response = self.client.put("/api/midi/profile", json=profile)

        self.assertEqual(response.status_code, 422)

    @staticmethod
    def _profile_payload() -> dict[str, Any]:
        def role(channel: int, low: int, high: int) -> dict[str, Any]:
            return {
                "primary_channel": channel,
                "candidates": [
                    {
                        "channel": channel,
                        "event_count": 8,
                        "notes": [low, high],
                        "confidence": 1.0,
                    }
                ],
                "note_min": low,
                "note_max": high,
                "event_count": 8,
                "confidence": 1.0,
            }

        return {
            "schema_version": 1,
            "detection_method": "guided-activity-v1",
            "input_port": "Accordion test input",
            "output_port": "Synth test output",
            "roles": {
                "treble": role(8, 48, 84),
                "bass": role(3, 36, 48),
                "chord": role(12, 48, 71),
            },
        }

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
