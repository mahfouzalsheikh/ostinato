from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import create_autospec

from fastapi.testclient import TestClient

from ostinato.arranger import LiveArrangerService
from ostinato.audio_output import (
    AudioOutputDevice,
    AudioOutputService,
    AudioOutputStore,
)
from ostinato.midi_profile import MidiProfileStore
from ostinato.realtime_midi import MidiService
from ostinato.style_designer import CustomStyleStore, default_custom_style_payload
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
        self.tested_audio_outputs: list[str] = []
        self.audio_output_store = AudioOutputStore(
            Path(self.temporary.name) / "audio-output.json"
        )
        self.audio_output_service = AudioOutputService(
            self.audio_output_store,
            discover=lambda: [
                AudioOutputDevice(
                    "plughw:CARD=Test,DEV=0",
                    "Test USB Audio · Analog Stereo",
                )
            ],
            test=self.tested_audio_outputs.append,
        )
        self.custom_style_store = CustomStyleStore(
            Path(self.temporary.name) / "custom-styles.json"
        )
        self.client_context = TestClient(
            create_app(
                self.service,
                self.profile_store,
                audio_output_service=self.audio_output_service,
                custom_style_store=self.custom_style_store,
            )
        )
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
        arranger_clock = self.client.get("/assets/arranger-clock.js")

        self.assertEqual(index.status_code, 200)
        self.assertIn("<fr4x-accordion", index.text)
        self.assertEqual(component.status_code, 200)
        self.assertEqual(surface_mapping.status_code, 200)
        self.assertEqual(stradella.status_code, 200)
        self.assertEqual(arranger_clock.status_code, 200)
        self.assertIn("PIANO_KEY_COUNT = 39", surface_mapping.text)
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
        self.assertIn('id="arranger-style"', index.text)
        self.assertIn('id="arranger-intro"', index.text)
        self.assertIn('id="arranger-ending"', index.text)
        self.assertIn('id="arranger-tempo-mode"', index.text)
        self.assertIn('id="arranger-fixed-tempo"', index.text)
        self.assertIn('id="arranger-beat-lights"', index.text)
        self.assertIn('id="arranger-beat-label"', index.text)
        self.assertIn('id="audio-output-dialog"', index.text)
        self.assertIn('id="audio-output-select"', index.text)
        self.assertIn('id="test-audio-output"', index.text)
        self.assertIn('id="open-style-designer"', index.text)
        self.assertIn('id="style-designer-dialog"', index.text)
        self.assertIn('id="designer-meter"', index.text)
        self.assertIn('id="designer-phrase-bars"', index.text)
        self.assertIn('id="designer-template"', index.text)
        self.assertIn('id="designer-save"', index.text)
        self.assertIn("Keys · guitars · basses · strings · winds", index.text)
        self.assertIn('data-field="octave"', index.text)
        self.assertIn('data-field="gate"', index.text)
        self.assertIn('id="designer-preview-tempo"', index.text)
        self.assertIn('id="designer-preview-play"', index.text)
        self.assertIn('id="designer-preview-stop"', index.text)
        self.assertNotIn("Configure the sound module", index.text)
        app_script = self.client.get("/assets/app.js")
        self.assertEqual(app_script.status_code, 200)
        self.assertIn("scheduleDesignerPreviewRestart", app_script.text)
        self.assertNotIn("Press Restart to hear the update", app_script.text)

    def test_arranger_catalog_and_safe_stopped_controls_are_available(self) -> None:
        initial = self.client.get("/api/arranger/status")
        selected = self.client.post(
            "/api/arranger/command",
            json={"action": "style", "value": "classic_waltz"},
        )
        synced = self.client.post(
            "/api/arranger/command",
            json={"action": "sync", "value": True},
        )

        self.assertEqual(initial.status_code, 200)
        self.assertEqual(
            [style["id"] for style in initial.json()["styles"]],
            [
                "modern_tango",
                "classic_tango",
                "classic_waltz",
                "bossa_nova",
                "swing_foxtrot",
                "alpine_polka",
                "motown_soul",
                "funk_pocket",
                "soft_pop",
                "country_two_step",
                "reggae_one_drop",
                "brazilian_samba",
                "new_orleans_chacha",
                "blues_shuffle",
            ],
        )
        self.assertEqual(
            sum(
                "CC BY 4.0" in style["provenance"] for style in initial.json()["styles"]
            ),
            8,
        )
        self.assertTrue(all(style["description"] for style in initial.json()["styles"]))
        self.assertEqual(selected.json()["style"], "classic_waltz")
        self.assertEqual(selected.json()["tempo_bpm"], 96)
        self.assertEqual(selected.json()["ticks_per_beat"], 96)
        self.assertIsNone(selected.json()["beat_index"])
        self.assertIs(synced.json()["sync_enabled"], True)

    def test_arranger_fixed_tempo_control_validates_and_updates_status(self) -> None:
        fixed = self.client.post(
            "/api/arranger/command",
            json={"action": "tempo", "value": 134},
        )
        invalid = self.client.post(
            "/api/arranger/command",
            json={"action": "tempo", "value": 300},
        )
        automatic = self.client.post(
            "/api/arranger/command",
            json={"action": "tempo_mode", "value": "bass_auto"},
        )

        self.assertEqual(fixed.status_code, 200)
        self.assertEqual(fixed.json()["tempo_bpm"], 134)
        self.assertEqual(fixed.json()["tempo_mode"], "fixed")
        self.assertEqual(invalid.status_code, 409)
        self.assertEqual(automatic.json()["tempo_mode"], "bass_auto")

    def test_custom_styles_can_be_created_edited_and_deleted(self) -> None:
        catalog = self.client.get("/api/styles")
        created = self.client.post(
            "/api/styles", json=default_custom_style_payload("classic_waltz")
        )
        style = created.json()
        edited_payload = default_custom_style_payload("classic_waltz")
        edited_payload["name"] = "Edited waltz"
        edited = self.client.put(f"/api/styles/{style['id']}", json=edited_payload)
        after_edit = self.client.get("/api/styles")
        deleted = self.client.delete(f"/api/styles/{style['id']}")

        self.assertEqual(catalog.status_code, 200)
        instrument_ids = {
            instrument["id"] for instrument in catalog.json()["instruments"]
        }
        self.assertTrue(
            {
                "none",
                "piano",
                "acoustic_guitar",
                "mandolin",
                "double_bass",
                "fingered_bass",
                "contrabass",
                "string_ensemble",
                "flute",
            }.issubset(instrument_ids)
        )
        self.assertEqual(catalog.json()["meters"], [2, 3, 4])
        self.assertEqual(catalog.json()["defaults"]["schema_version"], 2)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(edited.json()["name"], "Edited waltz")
        self.assertEqual(len(after_edit.json()["styles"]), 1)
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/styles").json()["styles"], [])

    def test_unsaved_style_preview_and_stop_reach_the_arranger(self) -> None:
        arranger = create_autospec(LiveArrangerService, instance=True)
        arranger.next_check_delay_seconds.return_value = 0.05
        arranger.advance.return_value = {"running": False}
        arranger.preview_custom_style.return_value = {
            "style_previewing": True,
            "preview_tempo_bpm": 146,
        }
        arranger.stop_style_preview.return_value = {
            "style_previewing": False,
            "preview_tempo_bpm": None,
        }
        service = MidiService(FakeMidiBackend(), poll_interval_seconds=0.01)
        app = create_app(
            service,
            MidiProfileStore(Path(self.temporary.name) / "preview-profile.json"),
            arranger_service=arranger,
            audio_output_service=self.audio_output_service,
            custom_style_store=self.custom_style_store,
        )

        with TestClient(app) as client:
            started = client.post(
                "/api/styles/preview",
                json={
                    "style": default_custom_style_payload("classic_waltz"),
                    "tempo_bpm": 146,
                },
            )
            stopped = client.delete("/api/styles/preview")

        self.assertEqual(started.status_code, 200)
        self.assertIs(started.json()["style_previewing"], True)
        self.assertEqual(stopped.status_code, 200)
        preview_style, preview_tempo = arranger.preview_custom_style.call_args.args
        self.assertEqual(preview_style.base_style_id, "classic_waltz")
        self.assertEqual(preview_tempo, 146)
        arranger.stop_style_preview.assert_called_once_with()

    def test_new_groove_pack_style_can_be_previewed(self) -> None:
        payload = default_custom_style_payload("funk_pocket")
        arranger = create_autospec(LiveArrangerService, instance=True)
        arranger.next_check_delay_seconds.return_value = 0.05
        arranger.advance.return_value = {
            "running": False,
            "output_configured": True,
        }
        arranger.preview_custom_style.return_value = {
            "style_previewing": True,
            "preview_tempo_bpm": 112,
        }
        app = create_app(
            MidiService(FakeMidiBackend()),
            MidiProfileStore(Path(self.temporary.name) / "groove-profile.json"),
            arranger,
            self.audio_output_service,
            CustomStyleStore(Path(self.temporary.name) / "groove-styles.json"),
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/styles/preview",
                json={"style": payload, "tempo_bpm": 112},
            )

        self.assertEqual(response.status_code, 200)
        preview_style, preview_tempo = arranger.preview_custom_style.call_args.args
        self.assertEqual(preview_style.base_style_id, "funk_pocket")
        self.assertEqual(preview_tempo, 112)

    def test_audio_output_is_discovered_tested_and_saved_by_exact_id(self) -> None:
        available = self.client.get("/api/audio/outputs")
        blocked_start = self.client.post(
            "/api/arranger/command", json={"action": "start"}
        )
        tested = self.client.post(
            "/api/audio/test", json={"device": "plughw:CARD=Test,DEV=0"}
        )
        saved = self.client.put(
            "/api/audio/output", json={"device": "plughw:CARD=Test,DEV=0"}
        )

        self.assertEqual(available.status_code, 200)
        self.assertEqual(
            available.json()["devices"],
            [
                {
                    "id": "plughw:CARD=Test,DEV=0",
                    "name": "Test USB Audio · Analog Stereo",
                }
            ],
        )
        self.assertEqual(blocked_start.status_code, 409)
        self.assertEqual(tested.status_code, 200)
        self.assertEqual(self.tested_audio_outputs, ["plughw:CARD=Test,DEV=0"])
        self.assertIs(saved.json()["available"], True)
        status = self.client.get("/api/arranger/status").json()
        self.assertEqual(status["output_mode"], "host_analog_audio")
        self.assertIs(status["output_configured"], True)

    def test_audio_output_rejects_identifier_not_in_current_discovery(self) -> None:
        response = self.client.put(
            "/api/audio/output", json={"device": "plughw:CARD=Missing,DEV=0"}
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("not currently available", response.json()["detail"])

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
        arranger = self.client.get("/api/arranger/status").json()
        self.assertEqual(arranger["bass_channel"], 3)
        self.assertEqual(arranger["chord_channel"], 12)
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
