from __future__ import annotations

import unittest
from typing import cast

from ostinato.arranger import (
    CHORD_COALESCE_NS,
    CHORD_MAX_COALESCE_NS,
    STYLE_PREVIEW_DURATION_NS,
    ArrangerError,
    BassTempoTracker,
    LiveArrangerService,
    classify_chord_notes,
    predict_harmony,
    style_rhythm_spans,
)
from ostinato.computer_audio import TRANSPORT_TICKS_PER_BEAT, DemoSection
from ostinato.domain import ChordQuality, ChordState
from ostinato.style_designer import CustomStyle, default_custom_style_payload
from ostinato.styles.models import Style
from tests.unit.test_imported_style_live import _style as imported_test_style


class FakeArrangerAudio:
    def __init__(self) -> None:
        self._section = DemoSection.STOPPED
        self.style = "modern_tango"
        self.tempo = 120
        self.chord: ChordState | None = None
        self.closed = False
        self.ending_requests = 0
        self.fill_requests: list[int] = []
        self.fill_variation: int | None = None
        self.device: str | None = None
        self.error: str | None = None
        self.position_ticks: int | None = 0
        self.custom_style: CustomStyle | None = None
        self.imported_style: Style | None = None

    @property
    def section(self) -> DemoSection:
        return self._section

    def select_style(
        self,
        style_id: str,
        custom_style: CustomStyle | None = None,
        imported_style: Style | None = None,
    ) -> None:
        self.style = style_id
        self.custom_style = custom_style
        self.imported_style = imported_style

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

    def request_fill(self, variation: int) -> None:
        self.fill_requests.append(variation)
        self.fill_variation = variation

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
            "treble": {"primary_channel": 1},
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

    def test_note_clusters_accept_inversions_and_octave_doubling(self) -> None:
        major = classify_chord_notes([55, 60, 64, 72])
        seventh_without_fifth = classify_chord_notes([58, 60, 64, 72])

        assert major is not None
        self.assertEqual(
            (major.root_pitch_class, major.quality),
            (0, ChordQuality.MAJOR),
        )
        assert seventh_without_fifth is not None
        self.assertEqual(
            (seventh_without_fifth.root_pitch_class, seventh_without_fifth.quality),
            (0, ChordQuality.DOMINANT_SEVENTH),
        )
        self.assertIsNone(classify_chord_notes([48, 49, 52, 55]))

    def test_prediction_distinguishes_new_root_from_alternating_bass_by_meter(
        self,
    ) -> None:
        d_minor = ChordState(2, ChordQuality.MINOR, None, 1.0, ("test",), 0)

        downbeat = predict_harmony(9, d_minor, harmonic_boundary=True)
        within_measure = predict_harmony(9, d_minor, harmonic_boundary=False)

        self.assertEqual(
            (downbeat.root_pitch_class, downbeat.quality),
            (9, ChordQuality.MAJOR),
        )
        self.assertEqual(
            (within_measure.root_pitch_class, within_measure.quality),
            (2, ChordQuality.MINOR),
        )

    def test_active_melody_can_select_a_seventh_or_preserve_prior_harmony(
        self,
    ) -> None:
        d_minor = ChordState(2, ChordQuality.MINOR, None, 1.0, ("test",), 0)

        a_seventh = predict_harmony(
            9, d_minor, active_melody_notes=(67,), harmonic_boundary=True
        )
        d_minor_over_a = predict_harmony(
            9, d_minor, active_melody_notes=(65,), harmonic_boundary=True
        )

        self.assertEqual(a_seventh.quality, ChordQuality.DOMINANT_SEVENTH)
        self.assertEqual(
            (d_minor_over_a.root_pitch_class, d_minor_over_a.quality),
            (2, ChordQuality.MINOR),
        )


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
        self.assertIsNone(self.audio.chord.bass_pitch_class)

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

    def test_chord_deadline_extends_from_the_latest_cluster_note(self) -> None:
        for note, timestamp in (
            (48, 0),
            (52, 4_000_000),
            (55, 8_000_000),
        ):
            self.arranger.handle_midi_event(midi_event(3, note, timestamp))

        still_pending = self.arranger.advance(CHORD_COALESCE_NS)
        status = self.arranger.advance(8_000_000 + CHORD_COALESCE_NS)

        self.assertIsNone(still_pending["chord"])
        self.assertEqual(status["chord"], "C")
        assert self.audio.chord is not None
        self.assertEqual(
            self.audio.chord.recognized_at_ns,
            8_000_000 + CHORD_COALESCE_NS,
        )

    def test_chord_cluster_has_a_bounded_maximum_wait(self) -> None:
        for note, timestamp in (
            (48, 0),
            (52, 8_000_000),
            (55, 16_000_000),
            (58, 23_000_000),
        ):
            self.arranger.handle_midi_event(midi_event(3, note, timestamp))

        status = self.arranger.advance(CHORD_MAX_COALESCE_NS)

        self.assertEqual(status["chord"], "C7")
        assert self.audio.chord is not None
        self.assertEqual(self.audio.chord.recognized_at_ns, CHORD_MAX_COALESCE_NS)

    def test_monitor_wait_tracks_chord_deadline_without_busy_polling(self) -> None:
        self.assertEqual(self.arranger.next_check_delay_seconds(now_ns=0), 0.05)
        self.arranger.handle_midi_event(midi_event(3, 48, 1_000_000))

        self.assertEqual(
            self.arranger.next_check_delay_seconds(now_ns=1_000_000),
            CHORD_COALESCE_NS / 1_000_000_000,
        )
        self.assertEqual(
            self.arranger.next_check_delay_seconds(now_ns=4_000_000),
            0.009,
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

    def test_downbeat_bass_predicts_then_melody_refines_and_chord_confirms(
        self,
    ) -> None:
        self.arranger.command("style", "classic_waltz")
        for note in (50, 53, 57):
            self.arranger.handle_midi_event(midi_event(3, note, 0))
        self.arranger.advance(CHORD_COALESCE_NS)
        self.arranger.command("start")
        self.audio.position_ticks = 3 * TRANSPORT_TICKS_PER_BEAT

        self.arranger.handle_midi_event(midi_event(2, 57, 20_000_000))
        bass_prediction = self.arranger.snapshot()
        self.arranger.handle_midi_event(midi_event(1, 67, 21_000_000))
        melody_refinement = self.arranger.snapshot()

        self.assertEqual(bass_prediction["chord"], "A")
        self.assertEqual(bass_prediction["harmony_source"], "bass + melody prediction")
        self.assertEqual(melody_refinement["chord"], "A7")
        self.assertEqual(melody_refinement["bass"], "A")
        assert self.audio.chord is not None
        self.assertIsNone(self.audio.chord.bass_pitch_class)
        self.assertLess(self.audio.chord.confidence, 1.0)

        for note in (50, 53, 57):
            self.arranger.handle_midi_event(midi_event(3, note, 30_000_000))
        confirmed = self.arranger.advance(30_000_000 + CHORD_COALESCE_NS)

        self.assertEqual(confirmed["chord"], "Dm")
        self.assertEqual(confirmed["harmony_source"], "chord button")
        self.assertIsNone(confirmed["prediction_confidence"])

    def test_non_downbeat_fifth_bass_keeps_the_confirmed_chord(self) -> None:
        for note in (50, 53, 57):
            self.arranger.handle_midi_event(midi_event(3, note, 0))
        self.arranger.advance(CHORD_COALESCE_NS)
        self.arranger.command("start")
        self.audio.position_ticks = TRANSPORT_TICKS_PER_BEAT

        self.arranger.handle_midi_event(midi_event(2, 57, 20_000_000))
        status = self.arranger.snapshot()

        self.assertEqual(status["chord"], "Dm")
        self.assertEqual(status["harmony_source"], "bass + melody prediction")

    def test_bass_note_does_not_choose_an_ambiguous_diminished_chord_root(
        self,
    ) -> None:
        self.arranger.handle_midi_event(midi_event(2, 51, 0))
        for note in (48, 51, 54, 57):
            self.arranger.handle_midi_event(midi_event(3, note, 0))

        status = self.arranger.advance(CHORD_COALESCE_NS)

        self.assertEqual(status["chord"], "Cdim")
        self.assertEqual(status["bass"], "Eb")
        assert self.audio.chord is not None
        self.assertEqual(self.audio.chord.root_pitch_class, 0)
        self.assertIsNone(self.audio.chord.bass_pitch_class)

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

    def test_two_fill_variations_are_available_only_during_main_playback(self) -> None:
        with self.assertRaisesRegex(ArrangerError, "main style"):
            self.arranger.command("fill", 1)
        self.arranger.command("start")

        first = self.arranger.command("fill", 1)
        second = self.arranger.command("fill", 2)

        self.assertEqual(self.audio.fill_requests, [1, 2])
        self.assertEqual(first["fill_variation"], 1)
        self.assertEqual(second["fill_variation"], 2)
        with self.assertRaisesRegex(ArrangerError, "variation 1 or 2"):
            self.arranger.command("fill", 3)

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

    def test_saved_custom_style_uses_its_template_tempo_and_audio_palette(self) -> None:
        value = default_custom_style_payload("classic_waltz")
        value["id"] = "custom-123456abcdef"
        value["name"] = "My small waltz"
        value["tempo_bpm"] = 104
        custom = CustomStyle.from_mapping(value)
        self.arranger.configure_custom_styles((custom,))

        status = self.arranger.command("style", custom.id)

        self.assertEqual(status["style"], custom.id)
        self.assertEqual(status["tempo_bpm"], 104)
        self.assertEqual(status["beats_per_bar"], 3)
        self.assertEqual(self.audio.style, "classic_waltz")
        self.assertEqual(self.audio.custom_style, custom)
        styles = cast(list[dict[str, object]], status["styles"])
        self.assertTrue(
            next(style for style in styles if style["id"] == custom.id)["custom"]
        )

    def test_local_import_is_selectable_and_exposes_its_meter_and_policy(self) -> None:
        imported = imported_test_style()
        self.arranger.configure_imported_styles((imported,))

        status = self.arranger.command("style", imported.id)

        self.assertEqual(status["style"], imported.id)
        self.assertEqual(status["beats_per_bar"], 2)
        self.assertEqual(self.audio.style, imported.id)
        self.assertEqual(self.audio.imported_style, imported)
        styles = cast(list[dict[str, object]], status["styles"])
        catalog_item = next(style for style in styles if style["id"] == imported.id)
        self.assertIs(catalog_item["imported"], True)
        self.assertEqual(catalog_item["group"], "KORG · Other imports")
        description = catalog_item["description"]
        self.assertIsInstance(description, str)
        assert isinstance(description, str)
        self.assertIn("Ostinato chord adaptation", description)

    def test_unsaved_preview_uses_independent_tempo_and_restores_audio(self) -> None:
        value = default_custom_style_payload("classic_waltz")
        value["id"] = "custom-123456abcdef"
        value["backing"] = {
            "instrument": "string_ensemble",
            "volume": 44,
            "octave": 1,
            "gate_percent": 130,
        }
        preview = CustomStyle.from_mapping(value)

        status = self.arranger.preview_custom_style(preview, 138)

        self.assertIs(status["style_previewing"], True)
        self.assertEqual(status["preview_tempo_bpm"], 138)
        self.assertEqual(status["style"], "modern_tango")
        self.assertEqual(self.audio.style, "classic_waltz")
        self.assertEqual(self.audio.custom_style, preview)
        self.assertEqual(self.audio.tempo, 138)
        assert self.audio.chord is not None
        self.assertEqual(self.audio.chord.name, "C")
        self.assertEqual(self.audio.section, DemoSection.MAIN)

        restored = self.arranger.stop_style_preview()

        self.assertIs(restored["style_previewing"], False)
        self.assertIsNone(restored["preview_tempo_bpm"])
        self.assertEqual(self.audio.style, "modern_tango")
        self.assertIsNone(self.audio.custom_style)
        self.assertEqual(self.audio.tempo, 120)
        self.assertIsNone(self.audio.chord)
        self.assertEqual(self.audio.section, DemoSection.STOPPED)

    def test_live_command_stops_preview_before_starting_arranger(self) -> None:
        value = default_custom_style_payload()
        value["id"] = "custom-123456abcdef"
        preview = CustomStyle.from_mapping(value)
        self.arranger.preview_custom_style(preview, 90)

        status = self.arranger.command("start")

        self.assertIs(status["style_previewing"], False)
        self.assertIs(status["running"], True)
        self.assertEqual(self.audio.style, "modern_tango")
        self.assertIsNone(self.audio.custom_style)
        self.assertEqual(self.audio.tempo, 120)

    def test_unsaved_preview_stops_automatically_after_bounded_audition(self) -> None:
        value = default_custom_style_payload()
        value["id"] = "custom-123456abcdef"
        preview = CustomStyle.from_mapping(value)
        self.arranger.preview_custom_style(preview, 110)

        self.now_ns = STYLE_PREVIEW_DURATION_NS
        status = self.arranger.advance()

        self.assertIs(status["style_previewing"], False)
        self.assertEqual(self.audio.style, "modern_tango")
        self.assertEqual(self.audio.tempo, 120)
        self.assertEqual(self.audio.section, DemoSection.STOPPED)

    def test_preview_requires_the_selected_audio_output(self) -> None:
        arranger = LiveArrangerService(FakeArrangerAudio())
        value = default_custom_style_payload()
        value["id"] = "custom-123456abcdef"
        preview = CustomStyle.from_mapping(value)

        with self.assertRaisesRegex(ArrangerError, "audio output"):
            arranger.preview_custom_style(preview, 120)

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
