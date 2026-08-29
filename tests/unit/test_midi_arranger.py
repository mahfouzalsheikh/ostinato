from __future__ import annotations

import time
import unittest
from typing import cast

from ostinato.computer_audio import DemoSection
from ostinato.domain import ChordQuality, ChordState
from ostinato.midi_arranger import (
    CLOSED_HIHAT_NOTE,
    KICK_NOTE,
    SECTION_BARS,
    TICKS_PER_QUARTER,
    MidiArrangerOutput,
    MidiRouting,
    plan_style_bar,
)
from ostinato.realtime_midi import MidiService


def chord() -> ChordState:
    return ChordState(
        root_pitch_class=0,
        quality=ChordQuality.MAJOR,
        bass_pitch_class=0,
        confidence=1.0,
        source_event_ids=("test",),
        recognized_at_ns=0,
    )


class RecordingMidi:
    def __init__(self) -> None:
        self.sent: list[tuple[int, ...]] = []
        self.releases = 0

    def send(self, values: tuple[int, ...], *, owner: object) -> dict[str, object]:
        self.sent.append(tuple(values))
        return {}

    def release(self, owner: object) -> None:
        self.releases += 1


class MidiStylePlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.routing = MidiRouting(5, 6, 10)

    def test_tango_bar_routes_bass_chord_and_documented_drums(self) -> None:
        events = plan_style_bar(
            style_id="modern_tango",
            section=DemoSection.MAIN,
            section_bar=0,
            start_tick=0,
            chord=chord(),
            routing=self.routing,
        )
        note_ons = [
            event.data
            for event in events
            if event.data and event.data[0] & 0xF0 == 0x90
        ]

        self.assertTrue(any(message[0] == 0x94 for message in note_ons))
        self.assertTrue(any(message[0] == 0x95 for message in note_ons))
        drum_notes = {message[1] for message in note_ons if message[0] == 0x99}
        self.assertIn(KICK_NOTE, drum_notes)
        self.assertIn(CLOSED_HIHAT_NOTE, drum_notes)
        self.assertEqual(events[-1].tick, 4 * TICKS_PER_QUARTER)
        self.assertIsNone(events[-1].data)

    def test_waltz_bar_has_three_quarter_note_boundary(self) -> None:
        events = plan_style_bar(
            style_id="classic_waltz",
            section=DemoSection.MAIN,
            section_bar=0,
            start_tick=500,
            chord=chord(),
            routing=self.routing,
        )

        self.assertEqual(events[-1].tick, 500 + (3 * TICKS_PER_QUARTER))

    def test_bass_and_chord_can_share_one_confirmed_melodic_channel(self) -> None:
        events = plan_style_bar(
            style_id="modern_tango",
            section=DemoSection.MAIN,
            section_bar=0,
            start_tick=0,
            chord=chord(),
            routing=MidiRouting(4, 4, 10),
        )
        melodic_notes = [
            event.data
            for event in events
            if event.data and event.data[0] & 0xF0 == 0x90 and event.data[0] != 0x99
        ]

        self.assertTrue(any(message[1] < 60 for message in melodic_notes))
        self.assertTrue(any(message[1] >= 60 for message in melodic_notes))
        self.assertEqual({message[0] for message in melodic_notes}, {0x93})

    def test_drum_channel_cannot_share_a_melodic_channel(self) -> None:
        with self.assertRaisesRegex(ValueError, "drum channel must differ"):
            MidiRouting(4, 5, 4)

    def test_intro_builds_and_final_ending_bar_reduces_orchestration(self) -> None:
        intro_first = plan_style_bar(
            style_id="modern_tango",
            section=DemoSection.INTRO,
            section_bar=0,
            start_tick=0,
            chord=chord(),
            routing=self.routing,
        )
        intro_last = plan_style_bar(
            style_id="modern_tango",
            section=DemoSection.INTRO,
            section_bar=SECTION_BARS - 1,
            start_tick=0,
            chord=chord(),
            routing=self.routing,
        )
        ending_last = plan_style_bar(
            style_id="modern_tango",
            section=DemoSection.ENDING,
            section_bar=SECTION_BARS - 1,
            start_tick=0,
            chord=chord(),
            routing=self.routing,
        )

        first_channels = {event.data[0] & 0x0F for event in intro_first if event.data}
        last_channels = {event.data[0] & 0x0F for event in intro_last if event.data}
        ending_channels = {event.data[0] & 0x0F for event in ending_last if event.data}
        self.assertEqual(first_channels, {5})
        self.assertEqual(last_channels, {4, 5, 9})
        self.assertEqual(ending_channels, {5})


class MidiArrangerOutputTests(unittest.TestCase):
    def test_dispatches_immediate_bar_events_and_releases_on_stop(self) -> None:
        recording = RecordingMidi()
        output = MidiArrangerOutput(cast(MidiService, recording))
        try:
            output.configure_routing(MidiRouting(5, 6, 10))
            output.set_chord(chord())
            output.start_main()
            deadline = time.monotonic() + 0.2
            while len(recording.sent) < 2 and time.monotonic() < deadline:
                time.sleep(0.005)

            output.stop()

            self.assertGreaterEqual(len(recording.sent), 2)
            self.assertTrue(any(message[1] == KICK_NOTE for message in recording.sent))
            self.assertGreaterEqual(recording.releases, 1)
            self.assertEqual(output.section, DemoSection.STOPPED)
        finally:
            output.close()


if __name__ == "__main__":
    unittest.main()
