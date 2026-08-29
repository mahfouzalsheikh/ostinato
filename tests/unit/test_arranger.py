from __future__ import annotations

import unittest

from ostinato.arranger import (
    CHORD_COALESCE_NS,
    ArrangerError,
    BassTempoTracker,
    LiveArrangerService,
    classify_chord_notes,
    style_rhythm_spans,
)
from ostinato.computer_audio import TRANSPORT_TICKS_PER_BEAT, DemoSection
from ostinato.domain import ChordQuality, ChordState


class FakeArrangerAudio:
    def __init__(self) -> None:
        self._section = DemoSection.STOPPED
        self.style = "modern_tango"
        self.tempo = 120
        self.chord: ChordState | None = None
        self.closed = False
        self.ending_requests = 0
        self.device: str | None = None
        self.error: str | None = None
        self.position_ticks: int | None = 0

    @property
    def section(self) -> DemoSection:
        return self._section

    def select_style(self, style_id: str) -> None:
        self.style = style_id

    def set_tempo(self, tempo_bpm: int) -> None:
        self.tempo = tempo_bpm

    def set_chord(self, chord: ChordState | None) -> None:
        self.chord = chord

    def start_main(self) -> None:
        self._section = DemoSection.MAIN

    def start_intro(self) -> None:
        self._section = DemoSection.INTRO

    def request_ending(self) -> None:
        self.ending_requests += 1
        self._section = DemoSection.ENDING

    def stop(self) -> None:
        self._section = DemoSection.STOPPED

    def close(self) -> None:
        self.closed = True

    def configure_output(self, device: str | None) -> None:
        self.device = device


def midi_event(channel: int, note: int, timestamp_ns: int) -> dict[str, object]:
    return {
        "type": "midi",
        "direction": "in",
        "channel": channel,
        "note": note,
        "timestamp_ns": timestamp_ns,
        "message_type": "note_on",
        "velocity": 96,
    }


def profile() -> dict[str, object]:
    return {
        "roles": {
            "bass": {"primary_channel": 2},
            "chord": {"primary_channel": 3},
        }
    }


class ChordClassifierTests(unittest.TestCase):
    def test_normal_and_documented_d_mode_chords_are_classified(self) -> None:
        major = classify_chord_notes([48, 52, 55])
        d_mode_minor = classify_chord_notes([60])

        assert major is not None
        self.assertEqual(major.root_pitch_class, 0)
        self.assertEqual(major.quality, ChordQuality.MAJOR)
        self.assertEqual(major.transmission, "notes")
        assert d_mode_minor is not None
        self.assertEqual(d_mode_minor.root_pitch_class, 0)
        self.assertEqual(d_mode_minor.quality, ChordQuality.MINOR)
        self.assertEqual(d_mode_minor.transmission, "d-mode")


class BassTempoTrackerTests(unittest.TestCase):
    def test_median_bass_intervals_produce_stable_tempo(self) -> None:
        tracker = BassTempoTracker()

        estimates = [
            tracker.observe(timestamp)
            for timestamp in (0, 500_000_000, 1_010_000_000, 1_500_000_000)
        ]

        self.assertEqual(estimates, [None, None, None, 120])

    def test_too_fast_duplicate_strokes_do_not_move_the_epoch(self) -> None:
        tracker = BassTempoTracker()

        tracker.observe(0, beat_spans=(0.25, 1.0))
        tracker.observe(100_000_000, beat_spans=(0.25, 1.0))
        tracker.observe(500_000_000, beat_spans=(0.25, 1.0))
        tracker.observe(1_000_000_000, beat_spans=(0.25, 1.0))
        estimate = tracker.observe(1_500_000_000, beat_spans=(0.25, 1.0))

        self.assertEqual(estimate, 120)

    def test_tango_three_three_two_gaps_normalize_to_quarter_note_tempo(self) -> None:
        tracker = BassTempoTracker()

        estimates = [
            tracker.observe(
                timestamp,
                beat_spans=(1.5, 1.5, 1.0),
                reference_bpm=120,
            )
            for timestamp in (0, 750_000_000, 1_500_000_000, 2_000_000_000)
        ]

        self.assertEqual(estimates, [None, None, None, 120])

    def test_half_note_bass_strokes_do_not_force_half_time(self) -> None:
        tracker = BassTempoTracker()

        estimates = [
            tracker.observe(
                timestamp,
                beat_spans=(1.0, 1.5, 2.0),
                reference_bpm=120,
            )
            for timestamp in (0, 1_000_000_000, 2_000_000_000, 3_000_000_000)
        ]

        self.assertEqual(estimates, [None, None, None, 120])

    def test_single_timing_outlier_does_not_destabilize_a_locked_tempo(self) -> None:
        tracker = BassTempoTracker()
        for timestamp in (0, 500_000_000, 1_000_000_000, 1_500_000_000):
            estimate = tracker.observe(timestamp)
        self.assertEqual(estimate, 120)

        outlier = tracker.observe(1_833_000_000)

        self.assertEqual(outlier, 120)

    def test_style_rhythm_spans_include_combined_bass_and_chord_movement(self) -> None:
        self.assertIn(0.5, style_rhythm_spans("modern_tango"))
        self.assertIn(1.5, style_rhythm_spans("modern_tango"))
        self.assertIn(0.67, style_rhythm_spans("swing_foxtrot"))


class LiveArrangerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now_ns = 0
        self.audio = FakeArrangerAudio()
        self.arranger = LiveArrangerService(self.audio, clock=lambda: self.now_ns)
        self.arranger.configure_profile(profile())
        self.arranger.configure_audio_output("plughw:CARD=Test,DEV=0")

    def test_bass_strokes_set_tempo_and_chord_cluster_sets_harmony(self) -> None:
        for timestamp in (0, 500_000_000, 1_000_000_000, 1_500_000_000):
            self.arranger.handle_midi_event(midi_event(2, 48, timestamp))
        for note in (48, 52, 55):
            self.arranger.handle_midi_event(midi_event(3, note, 1_600_000_000))

        status = self.arranger.advance(1_612_000_000)

        self.assertEqual(status["tempo_bpm"], 120)
        self.assertEqual(status["tempo_source"], "left hand · bass + chords")
        self.assertEqual(status["chord"], "C")
        assert self.audio.chord is not None
        self.assertEqual(self.audio.chord.bass_pitch_class, 0)

    def test_alternating_bass_and_chord_attacks_drive_auto_tempo(self) -> None:
        self.arranger.handle_midi_event(midi_event(2, 48, 0))
        self.arranger.handle_midi_event(midi_event(3, 48, 250_000_000))
        self.arranger.handle_midi_event(midi_event(2, 55, 500_000_000))
        self.arranger.handle_midi_event(midi_event(3, 48, 750_000_000))

        status = self.arranger.snapshot()

        self.assertEqual(status["tempo_bpm"], 120)
        self.assertEqual(status["tempo_source"], "left hand · bass + chords")

    def test_chord_attacks_can_drive_auto_tempo_without_bass(self) -> None:
        for timestamp in (0, 500_000_000, 1_000_000_000, 1_500_000_000):
            self.arranger.handle_midi_event(midi_event(3, 48, timestamp))

        status = self.arranger.advance(1_500_000_000 + CHORD_COALESCE_NS)

        self.assertEqual(status["tempo_bpm"], 120)
        self.assertEqual(status["tempo_source"], "left hand · chords")

    def test_chord_deadline_is_measured_from_first_not_last_cluster_note(self) -> None:
        for note, timestamp in (
            (48, 0),
            (52, 2_000_000),
            (55, 4_000_000),
        ):
            self.arranger.handle_midi_event(midi_event(3, note, timestamp))

        status = self.arranger.advance(CHORD_COALESCE_NS)

        self.assertEqual(status["chord"], "C")
        assert self.audio.chord is not None
        self.assertEqual(self.audio.chord.recognized_at_ns, CHORD_COALESCE_NS)

    def test_monitor_wait_tracks_chord_deadline_without_busy_polling(self) -> None:
        self.assertEqual(self.arranger.next_check_delay_seconds(now_ns=0), 0.05)
        self.arranger.handle_midi_event(midi_event(3, 48, 1_000_000))

        self.assertEqual(
            self.arranger.next_check_delay_seconds(now_ns=1_000_000),
            CHORD_COALESCE_NS / 1_000_000_000,
        )
        self.assertEqual(
            self.arranger.next_check_delay_seconds(now_ns=4_000_000),
            0.003,
        )

    def test_new_chord_cluster_ignores_notes_still_held_from_previous_chord(
        self,
    ) -> None:
        for note in (48, 52, 55):
            self.arranger.handle_midi_event(midi_event(3, note, 0))
        self.arranger.advance(CHORD_COALESCE_NS)

        for note in (55, 59, 62):
            self.arranger.handle_midi_event(midi_event(3, note, 20_000_000))
        status = self.arranger.advance(20_000_000 + CHORD_COALESCE_NS)

        self.assertEqual(status["chord"], "G")
        assert self.audio.chord is not None
        self.assertEqual(self.audio.chord.root_pitch_class, 7)

    def test_bass_flow_updates_the_current_harmony_without_waiting_for_a_chord(
        self,
    ) -> None:
        self.arranger.handle_midi_event(midi_event(2, 48, 0))
        for note in (48, 52, 55):
            self.arranger.handle_midi_event(midi_event(3, note, 0))
        self.arranger.advance(CHORD_COALESCE_NS)

        self.arranger.handle_midi_event(midi_event(2, 55, 20_000_000))
        status = self.arranger.snapshot()

        self.assertEqual(status["chord"], "C/G")
        self.assertEqual(status["bass"], "G")
        assert self.audio.chord is not None
        self.assertEqual(self.audio.chord.bass_pitch_class, 7)
        self.assertEqual(self.audio.chord.recognized_at_ns, 20_000_000)

    def test_sync_arms_intro_starts_on_left_hand_and_stops_after_two_bars(self) -> None:
        self.arranger.command("sync", True)
        armed = self.arranger.command("intro")
        self.assertEqual(armed["section"], "intro_armed")

        self.arranger.handle_midi_event(midi_event(2, 48, 0))
        started = self.arranger.snapshot()
        self.assertTrue(started["running"])
        self.assertEqual(started["section"], "intro")

        stopped = self.arranger.advance(4_000_000_000)
        self.assertFalse(stopped["running"])
        self.assertEqual(stopped["section"], "stopped")

    def test_style_change_requires_stop_and_applies_style_default_tempo(self) -> None:
        self.arranger.command("start")
        with self.assertRaises(ArrangerError):
            self.arranger.command("style", "classic_waltz")

        self.arranger.command("stop")
        status = self.arranger.command("style", "classic_waltz")

        self.assertEqual(status["style"], "classic_waltz")
        self.assertEqual(status["tempo_bpm"], 96)
        self.assertEqual(status["beats_per_bar"], 3)
        self.assertEqual(self.audio.style, "classic_waltz")

    def test_status_exposes_meter_aware_integer_transport_position(self) -> None:
        self.arranger.command("start")
        self.audio.position_ticks = (6 * TRANSPORT_TICKS_PER_BEAT) + 24

        four_four = self.arranger.snapshot()
        self.arranger.command("stop")
        self.arranger.command("style", "classic_waltz")
        self.arranger.command("start")
        three_four = self.arranger.snapshot()

        self.assertEqual(four_four["ticks_per_beat"], TRANSPORT_TICKS_PER_BEAT)
        self.assertEqual(four_four["position_ticks"], 600)
        self.assertEqual(four_four["beat_index"], 2)
        self.assertEqual(three_four["beat_index"], 0)

    def test_stopped_status_has_no_active_transport_beat(self) -> None:
        self.audio.position_ticks = 2 * TRANSPORT_TICKS_PER_BEAT

        status = self.arranger.snapshot()

        self.assertIsNone(status["position_ticks"])
        self.assertIsNone(status["beat_index"])

    def test_ending_and_panic_reach_audio_boundary(self) -> None:
        self.arranger.command("start")
        ending = self.arranger.command("ending")
        self.assertEqual(ending["section"], "ending")
        self.assertEqual(self.audio.ending_requests, 1)

        panic = self.arranger.command("panic")
        self.assertFalse(panic["running"])
        self.assertIsNone(self.audio.chord)

    def test_asynchronous_audio_failure_is_visible_and_stops_status(self) -> None:
        self.arranger.command("start")
        self.audio.error = "aplay stopped unexpectedly: device busy"

        status = self.arranger.advance()

        self.assertFalse(status["running"])
        error = status["error"]
        self.assertIsInstance(error, str)
        assert isinstance(error, str)
        self.assertIn("device busy", error)

    def test_fixed_tempo_ignores_bass_timing_until_auto_is_restored(self) -> None:
        fixed = self.arranger.command("tempo", 132)
        for timestamp in (0, 750_000_000, 1_500_000_000, 2_000_000_000):
            self.arranger.handle_midi_event(midi_event(2, 48, timestamp))

        unchanged = self.arranger.snapshot()
        automatic = self.arranger.command("tempo_mode", "bass_auto")

        self.assertEqual(fixed["tempo_mode"], "fixed")
        self.assertEqual(unchanged["tempo_bpm"], 132)
        self.assertEqual(unchanged["tempo_source"], "fixed control")
        self.assertEqual(automatic["tempo_mode"], "bass_auto")
        self.assertEqual(
            automatic["tempo_source"],
            "left-hand auto · waiting for bass or chord",
        )


if __name__ == "__main__":
    unittest.main()
