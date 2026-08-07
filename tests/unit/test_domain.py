from __future__ import annotations

import unittest

from ostinato.domain import ChordQuality, ChordState


class ChordStateTests(unittest.TestCase):
    def test_names_supported_chord_qualities(self) -> None:
        expected = {
            ChordQuality.MAJOR: "C",
            ChordQuality.MINOR: "Cm",
            ChordQuality.DOMINANT_SEVENTH: "C7",
            ChordQuality.DIMINISHED: "Cdim",
        }

        for quality, name in expected.items():
            with self.subTest(quality=quality):
                chord = ChordState(0, quality, None, 1.0, ("test",), 42)
                self.assertEqual(chord.name, name)

    def test_rejects_invalid_pitch_class(self) -> None:
        with self.assertRaisesRegex(ValueError, "root_pitch_class"):
            ChordState(12, ChordQuality.MAJOR, None, 1.0, ("test",), 42)

    def test_serializes_enum_and_display_name(self) -> None:
        chord = ChordState(10, ChordQuality.MINOR, 3, 0.75, ("event-1",), 42)

        result = chord.to_dict()

        self.assertEqual(result["quality"], "minor")
        self.assertEqual(result["name"], "Bbm")
        self.assertEqual(result["bass_pitch_class"], 3)


if __name__ == "__main__":
    unittest.main()
