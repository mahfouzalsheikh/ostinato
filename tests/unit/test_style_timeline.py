from __future__ import annotations

import unittest

from ostinato.computer_audio import DEMO_STYLES
from ostinato.style_designer import CustomStyle, default_custom_style_payload
from ostinato.style_timeline import built_in_style_timeline, custom_style_timeline


class StyleTimelineTests(unittest.TestCase):
    def test_every_builtin_exposes_five_bounded_musical_lanes(self) -> None:
        for style_id in DEMO_STYLES:
            with self.subTest(style=style_id):
                timeline = built_in_style_timeline(style_id)
                self.assertEqual(
                    [lane["id"] for lane in timeline["lanes"]],
                    ["bass", "comp", "fill", "backing", "drums"],
                )
                self.assertEqual(len(timeline["bar_dynamics"]), timeline["phrase_bars"])
                for lane in timeline["lanes"]:
                    self.assertTrue(lane["instrument"])
                    self.assertGreaterEqual(lane["level"], 0)
                    self.assertLessEqual(lane["level"], 100)
                    for event in lane["events"]:
                        self.assertGreaterEqual(event["start"], 0)
                        self.assertLess(event["start"], timeline["total_beats"])
                        self.assertGreater(event["duration"], 0)

    def test_custom_style_changes_phrase_palette_gate_and_disabled_drums(self) -> None:
        payload = default_custom_style_payload("classic_waltz")
        payload.update(name="Short waltz", phrase_bars=2, drums_enabled=False)
        payload["fill"] = {
            "instrument": "clarinet",
            "volume": 61,
            "octave": 0,
            "gate_percent": 50,
        }
        style = CustomStyle.from_mapping(payload, require_id=False)
        original = built_in_style_timeline("classic_waltz")
        timeline = custom_style_timeline(style)

        self.assertEqual(timeline["phrase_bars"], 2)
        self.assertEqual(timeline["total_beats"], 6)
        fill = next(lane for lane in timeline["lanes"] if lane["id"] == "fill")
        original_fill = next(lane for lane in original["lanes"] if lane["id"] == "fill")
        drums = next(lane for lane in timeline["lanes"] if lane["id"] == "drums")
        self.assertEqual(fill["instrument"], "Clarinet")
        self.assertEqual(fill["level"], 61)
        self.assertEqual(
            fill["events"][0]["duration"],
            original_fill["events"][0]["duration"] * 0.5,
        )
        self.assertEqual(drums["instrument"], "Off")
        self.assertEqual(drums["level"], 0)

    def test_research_driven_profiles_surface_new_defining_instruments(self) -> None:
        expectations = {
            "swing_foxtrot": "Trumpet",
            "alpine_polka": "Clarinet",
            "motown_soul": "Trumpet",
            "funk_pocket": "Trumpet",
            "new_orleans_chacha": "Trumpet",
        }
        for style_id, expected in expectations.items():
            with self.subTest(style=style_id):
                timeline = built_in_style_timeline(style_id)
                fill = next(lane for lane in timeline["lanes"] if lane["id"] == "fill")
                self.assertEqual(fill["instrument"], expected)
