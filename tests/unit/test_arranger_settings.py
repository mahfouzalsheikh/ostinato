from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ostinato.arranger_settings import (
    ArrangerSettingsStore,
    ArrangerSettingsStoreError,
)


class ArrangerSettingsStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = ArrangerSettingsStore(Path(self.temporary.name) / "routing.json")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_confirmed_routing_round_trips(self) -> None:
        routing = {
            "schema_version": 1,
            "output_mode": "fr4x_midi",
            "confirmed": True,
            "part_mode": "native",
            "detection_method": "guided-audible-confirmation-v1",
            "bass_channel": 2,
            "chord_channel": 3,
            "drum_channel": 10,
            "output_port": "Accordion output",
            "verified_parts": {"bass": True, "chord": True, "drum": True},
        }

        self.assertEqual(self.store.save(routing), routing)
        self.assertEqual(self.store.load(), routing)

    def test_unknown_schema_is_rejected(self) -> None:
        with self.assertRaises(ArrangerSettingsStoreError):
            self.store.save({"schema_version": 99})


if __name__ == "__main__":
    unittest.main()
