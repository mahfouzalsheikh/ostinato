from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ostinato.midi_profile import MidiProfileStore, MidiProfileStoreError


class MidiProfileStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "state" / "midi-profile.json"
        self.store = MidiProfileStore(self.path)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_missing_profile_loads_as_none_and_clear_is_idempotent(self) -> None:
        self.assertIsNone(self.store.load())
        self.store.clear()
        self.assertIsNone(self.store.load())

    def test_profile_is_saved_and_atomically_replaced(self) -> None:
        first = {"schema_version": 1, "input_port": "first"}
        second = {"schema_version": 1, "input_port": "second"}

        self.assertEqual(self.store.save(first), first)
        self.assertEqual(self.store.save(second), second)

        self.assertEqual(self.store.load(), second)
        self.assertEqual(list(self.path.parent.glob(".*.tmp")), [])

    def test_invalid_json_is_reported(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text("not json", encoding="utf-8")

        with self.assertRaisesRegex(MidiProfileStoreError, "could not read"):
            self.store.load()

    def test_unsupported_schema_is_rejected_on_read_and_write(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")

        with self.assertRaisesRegex(MidiProfileStoreError, "unsupported"):
            self.store.load()
        with self.assertRaisesRegex(MidiProfileStoreError, "unsupported"):
            self.store.save({"schema_version": 99})


if __name__ == "__main__":
    unittest.main()
