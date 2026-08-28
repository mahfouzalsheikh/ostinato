from __future__ import annotations

import unittest

from ostinato.midi_detection import (
    MidiDetectionError,
    NoteObservation,
    detect_midi_roles,
)


def notes(channel: int, *values: int) -> tuple[NoteObservation, ...]:
    return tuple(NoteObservation(channel=channel, note=value) for value in values)


class MidiDetectionTests(unittest.TestCase):
    def test_distinct_observed_channels_are_detected_with_full_confidence(self) -> None:
        detections = detect_midi_roles(
            {
                "treble": notes(7, 48, 52, 55, 60, 64, 67, 71, 84),
                "bass": notes(2, 36, 38, 40, 41, 43, 45, 47, 48),
                "chord": notes(11, 48, 52, 55, 50, 53, 57, 47, 51),
            }
        )

        self.assertEqual(detections["treble"]["primary_channel"], 7)
        self.assertEqual(detections["treble"]["note_min"], 48)
        self.assertEqual(detections["treble"]["note_max"], 84)
        self.assertEqual(detections["treble"]["confidence"], 1.0)
        self.assertEqual(detections["bass"]["primary_channel"], 2)
        self.assertEqual(detections["chord"]["primary_channel"], 11)

    def test_activity_shared_between_roles_is_reported_as_ambiguous(self) -> None:
        detections = detect_midi_roles(
            {
                "treble": notes(4, 60, 62, 64, 65),
                "bass": notes(2, 36, 38, 40, 41),
                "chord": notes(4, 48, 52, 55, 59),
            }
        )

        self.assertLess(float(detections["treble"]["confidence"]), 0.75)
        self.assertLess(float(detections["chord"]["confidence"]), 0.75)

    def test_every_guided_role_requires_observed_note_activity(self) -> None:
        with self.assertRaisesRegex(MidiDetectionError, "no note activity.*chord"):
            detect_midi_roles(
                {
                    "treble": notes(1, 60),
                    "bass": notes(2, 36),
                    "chord": (),
                }
            )


if __name__ == "__main__":
    unittest.main()
