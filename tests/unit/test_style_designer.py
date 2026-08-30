from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import cast

from ostinato.style_designer import (
    CustomStyleError,
    CustomStyleStore,
    default_custom_style_payload,
)


class CustomStyleStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = CustomStyleStore(Path(self.temporary.name) / "styles.json")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_create_update_reload_and_delete_a_style(self) -> None:
        created = self.store.create(default_custom_style_payload())
        changed = created.to_dict()
        changed["name"] = "Quiet tango"
        changed["tempo_bpm"] = 108

        updated = self.store.update(created.id, changed)
        reloaded = self.store.load()
        self.store.delete(created.id)

        self.assertTrue(created.id.startswith("custom-"))
        self.assertEqual(updated.name, "Quiet tango")
        self.assertEqual(updated.tempo_bpm, 108)
        self.assertEqual(reloaded, (updated,))
        self.assertEqual(self.store.load(), ())

    def test_rejects_unknown_instruments_and_templates(self) -> None:
        unsupported_instrument = default_custom_style_payload()
        unsupported_instrument["fill"] = {
            "instrument": "invented",
            "volume": 50,
        }
        unsupported_template = default_custom_style_payload()
        unsupported_template["base_style_id"] = "invented"

        with self.assertRaisesRegex(CustomStyleError, "unsupported instrument"):
            self.store.create(unsupported_instrument)
        with self.assertRaisesRegex(CustomStyleError, "rhythmic template"):
            self.store.create(unsupported_template)

    def test_advanced_measure_register_and_articulation_are_persisted(self) -> None:
        value = default_custom_style_payload("alpine_polka")
        value["phrase_bars"] = 2
        value["bass"] = {
            "instrument": "fingered_bass",
            "volume": 74,
            "octave": -1,
            "gate_percent": 65,
        }
        value["backing"] = {
            "instrument": "string_ensemble",
            "volume": 42,
            "octave": 1,
            "gate_percent": 130,
        }

        style = self.store.create(value)

        self.assertEqual(style.schema_version, 2)
        self.assertEqual(style.beats_per_bar, 2)
        self.assertEqual(style.phrase_bars, 2)
        self.assertEqual(style.bass.instrument, "fingered_bass")
        self.assertEqual(style.bass.octave, -1)
        self.assertEqual(style.backing.gate_percent, 130)

    def test_rejects_measure_template_mismatch_and_invalid_register(self) -> None:
        wrong_measure = default_custom_style_payload("classic_waltz")
        wrong_measure["beats_per_bar"] = 4
        invalid_register = default_custom_style_payload()
        invalid_register["fill"] = {
            "instrument": "flute",
            "volume": 50,
            "octave": 3,
            "gate_percent": 100,
        }

        with self.assertRaisesRegex(CustomStyleError, "requires a 3/4 measure"):
            self.store.create(wrong_measure)
        with self.assertRaisesRegex(CustomStyleError, "octave"):
            self.store.create(invalid_register)

    def test_missing_document_is_an_empty_catalog(self) -> None:
        self.assertEqual(self.store.load(), ())

    def test_schema_one_style_is_migrated_with_advanced_defaults(self) -> None:
        value = default_custom_style_payload("classic_waltz")
        value["schema_version"] = 1
        value["id"] = "custom-123456abcdef"
        value.pop("beats_per_bar")
        value.pop("phrase_bars")
        for name in ("bass", "comp", "fill", "backing"):
            layer = cast(dict[str, object], value[name])
            layer.pop("octave")
            layer.pop("gate_percent")
        self.store.path.write_text(
            json.dumps({"schema_version": 1, "styles": [value]}),
            encoding="utf-8",
        )

        (migrated,) = self.store.load()

        self.assertEqual(migrated.schema_version, 2)
        self.assertEqual(migrated.beats_per_bar, 3)
        self.assertEqual(migrated.phrase_bars, 4)
        self.assertEqual(migrated.comp.octave, 0)
        self.assertEqual(migrated.comp.gate_percent, 100)


if __name__ == "__main__":
    unittest.main()
