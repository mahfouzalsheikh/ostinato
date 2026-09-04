"""Backend-owned controls for the procedural live-arranger prototype.

The service consumes only channels saved by the guided MIDI profile. It keeps
tempo estimation, chord clustering, transport state, and audio ownership out of
the browser so reloading the display does not stop accompaniment.
"""

from __future__ import annotations

import math
import os
import statistics
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from itertools import pairwise
from typing import Protocol, cast

from ostinato.computer_audio import (
    DEMO_STYLES,
    TRANSPORT_TICKS_PER_BEAT,
    AudioPlaybackError,
    DemoAudioConfig,
    DemoSection,
    DemoStyleDefinition,
    PcmSink,
    RealtimeDemoArranger,
    open_pcm_sink,
)
from ostinato.domain import PITCH_CLASS_NAMES, ChordQuality, ChordState
from ostinato.keyboard_input import MAX_TEMPO_BPM, MIN_TEMPO_BPM
from ostinato.performance_controls import PerformanceControlAction
from ostinato.sfz_audio import (
    SfzStyleArrangementRenderer,
    SfzStylePaths,
    SfzWaltzArrangementRenderer,
    SfzWaltzPaths,
)
from ostinato.soundfont_audio import SoundFontArrangementRenderer
from ostinato.style_designer import CustomStyle
from ostinato.styles.controls import StyleControls
from ostinato.styles.groups import (
    CUSTOM_STYLE_GROUP,
    imported_style_group,
    musical_style_group,
)
from ostinato.styles.live_audio import (
    ImportedStyleArrangementRenderer,
    imported_style_playback_info,
    imported_style_rhythm_spans,
)
from ostinato.styles.models import Style, StyleTrackRole

JsonObject = dict[str, object]
CHORD_COALESCE_NS = 12_000_000
CHORD_MAX_COALESCE_NS = 24_000_000
MIN_LEFT_HAND_ATTACK_GAP_NS = 110_000_000
SYNC_STOP_BARS = 2
STYLE_PREVIEW_DURATION_NS = 30_000_000_000
RECENT_MELODY_NOTE_COUNT = 16
TEMPO_MODE_AUTO = "bass_auto"
TEMPO_MODE_FIXED = "fixed"


class ArrangerError(RuntimeError):
    """An arranger command could not be completed safely."""


@dataclass(frozen=True, slots=True)
class RecognizedChord:
    """Documented chord result before conversion to shared domain state."""

    root_pitch_class: int
    quality: ChordQuality
    transmission: str


@dataclass(frozen=True, slots=True)
class HarmonyPrediction:
    """One causal harmony estimate made before the chord button arrives."""

    root_pitch_class: int
    quality: ChordQuality
    confidence: float


_CHORD_INTERVALS: dict[ChordQuality, tuple[int, ...]] = {
    ChordQuality.MAJOR: (0, 4, 7),
    ChordQuality.MINOR: (0, 3, 7),
    ChordQuality.DOMINANT_SEVENTH: (0, 4, 7, 10),
    ChordQuality.DIMINISHED: (0, 3, 6),
}

_CHORD_QUALITY_PRIORS = {
    ChordQuality.MAJOR: 0.4,
    ChordQuality.MINOR: 0.3,
    ChordQuality.DOMINANT_SEVENTH: 0.1,
    ChordQuality.DIMINISHED: -0.4,
}


def _pitch_class_mask(root: int, intervals: Sequence[int]) -> int:
    mask = 0
    for interval in intervals:
        mask |= 1 << ((root + interval) % 12)
    return mask


_CHORD_TONE_MASKS = {
    (root, quality): _pitch_class_mask(root, intervals)
    for root in range(12)
    for quality, intervals in _CHORD_INTERVALS.items()
}

_CLASSIFIED_CHORDS: dict[int, RecognizedChord] = {}
for _quality, _intervals in (
    (ChordQuality.DOMINANT_SEVENTH, (0, 4, 7, 10)),
    (ChordQuality.DOMINANT_SEVENTH, (0, 4, 10)),
    (ChordQuality.DIMINISHED, (0, 3, 6, 9)),
    (ChordQuality.DIMINISHED, (0, 3, 6)),
    (ChordQuality.MAJOR, (0, 4, 7)),
    (ChordQuality.MINOR, (0, 3, 7)),
):
    for _root in range(12):
        _CLASSIFIED_CHORDS.setdefault(
            _pitch_class_mask(_root, _intervals),
            RecognizedChord(_root, _quality, "notes"),
        )


def classify_chord_notes(notes: Sequence[int]) -> RecognizedChord | None:
    """Classify normal chord clusters and documented FR-4X D-Mode codes."""

    valid = [note for note in notes if 0 <= note <= 127]
    if not valid:
        return None
    if len(valid) == 1 and 48 <= valid[0] <= 95:
        offset = valid[0] - 48
        qualities = (
            ChordQuality.MAJOR,
            ChordQuality.MINOR,
            ChordQuality.DOMINANT_SEVENTH,
            ChordQuality.DIMINISHED,
        )
        return RecognizedChord(offset % 12, qualities[offset // 12], "d-mode")

    actual_mask = 0
    for note in valid:
        actual_mask |= 1 << (note % 12)
    return _CLASSIFIED_CHORDS.get(actual_mask)


def predict_harmony(
    bass_pitch_class: int,
    previous_chord: ChordState | None,
    *,
    active_melody_notes: Sequence[int] = (),
    recent_melody_notes: Sequence[int] = (),
    harmonic_boundary: bool = True,
) -> HarmonyPrediction:
    """Rank conservative chord candidates from causal performance evidence.

    A bass onset can either continue the confirmed chord (including an
    alternating-fifth bass) or announce a chord rooted on the new bass note.
    Active melody has the strongest weight, recent melody supplies weak tonal
    context, and a bar boundary makes a root change more plausible.
    """

    if not 0 <= bass_pitch_class <= 11:
        raise ValueError("bass_pitch_class must be between 0 and 11")
    active_mask = 0
    for note in active_melody_notes:
        active_mask |= 1 << (note % 12)
    active_count = active_mask.bit_count()
    recent_counts = [0] * 12
    for note in recent_melody_notes:
        recent_counts[note % 12] += 1
    recent_count = len(recent_melody_notes)

    candidates = [(bass_pitch_class, quality) for quality in ChordQuality]
    if previous_chord is not None:
        previous = (previous_chord.root_pitch_class, previous_chord.quality)
        if previous not in candidates:
            candidates.append(previous)

    scored: list[tuple[float, int, int, int, ChordQuality]] = []
    for root, quality in candidates:
        intervals = _CHORD_INTERVALS[quality]
        tone_mask = _CHORD_TONE_MASKS[root, quality]
        score = _CHORD_QUALITY_PRIORS[quality]
        same_as_previous = (
            previous_chord is not None
            and root == previous_chord.root_pitch_class
            and quality == previous_chord.quality
        )
        if same_as_previous:
            score += 0.75 if harmonic_boundary else 2.25
        if previous_chord is not None:
            if root == previous_chord.root_pitch_class:
                score += 0.5
            root_motion = (bass_pitch_class - previous_chord.root_pitch_class) % 12
            if root == bass_pitch_class and root_motion in {5, 7}:
                score += 1.25
            if (
                root == bass_pitch_class
                and root_motion == 7
                and previous_chord.quality is ChordQuality.MINOR
                and quality in {ChordQuality.MAJOR, ChordQuality.DOMINANT_SEVENTH}
            ):
                score += 0.4
        if root == bass_pitch_class:
            score += 2.5 if harmonic_boundary else 0.25
        elif tone_mask & (1 << bass_pitch_class):
            score += 0.75 if harmonic_boundary else 1.75
        else:
            score -= 2.0
        matching_active_count = (active_mask & tone_mask).bit_count()
        score += (3.0 * matching_active_count) - (
            2.0 * (active_count - matching_active_count)
        )
        matching_recent_count = sum(
            recent_counts[(root + interval) % 12] for interval in intervals
        )
        score += (0.12 * matching_recent_count) - (
            0.04 * (recent_count - matching_recent_count)
        )
        if quality is ChordQuality.DOMINANT_SEVENTH and active_mask & (
            1 << ((root + 10) % 12)
        ):
            score += 1.0
        scored.append((score, int(same_as_previous), -len(intervals), -root, quality))

    scored.sort(reverse=True)
    best_score, _continuity, _complexity, negative_root, best_quality = scored[0]
    runner_up_score = scored[1][0] if len(scored) > 1 else best_score
    best_root = -negative_root
    margin = max(0.0, best_score - runner_up_score)
    confidence = min(0.95, 0.55 + (0.1 * margin))
    return HarmonyPrediction(best_root, best_quality, confidence)


class BassTempoTracker:
    """Estimate quarter-note tempo from a robust left-hand attack stream.

    The historic class name is retained for API compatibility. Callers may feed
    deduplicated bass and chord attacks and provide the possible musical spans
    between those attacks.
    """

    def __init__(
        self,
        *,
        window_size: int = 5,
        minimum_attack_gap_ns: int = MIN_LEFT_HAND_ATTACK_GAP_NS,
    ) -> None:
        if window_size < 2:
            raise ValueError("window_size must be at least two")
        if minimum_attack_gap_ns < 0:
            raise ValueError("minimum_attack_gap_ns cannot be negative")
        self._last_stroke_ns: int | None = None
        self._intervals_ns: deque[int] = deque(maxlen=window_size)
        self._minimum_attack_gap_ns = minimum_attack_gap_ns
        self._stable_bpm: int | None = None

    def reset(self) -> None:
        """Discard timing history after a style or manual transport reset."""

        self._last_stroke_ns = None
        self._intervals_ns.clear()
        self._stable_bpm = None

    def observe(
        self,
        timestamp_ns: int,
        *,
        beat_spans: Sequence[float] = (1.0,),
        reference_bpm: int = 120,
    ) -> int | None:
        """Normalize style-specific stroke gaps into a robust quarter-note BPM."""

        spans = tuple(span for span in beat_spans if span > 0)
        if timestamp_ns < 0 or not spans:
            return None
        previous = self._last_stroke_ns
        if previous is None:
            self._last_stroke_ns = timestamp_ns
            return None
        interval = timestamp_ns - previous
        minimum = max(
            self._minimum_attack_gap_ns,
            round(60_000_000_000 * min(spans) / MAX_TEMPO_BPM),
        )
        if interval < minimum:
            return None
        self._last_stroke_ns = timestamp_ns
        candidates: list[tuple[float, int]] = []
        for span in set(spans):
            beat_interval = round(interval / span)
            bpm = 60_000_000_000 / beat_interval
            if MIN_TEMPO_BPM <= bpm <= MAX_TEMPO_BPM:
                distance = abs(math.log(bpm / reference_bpm))
                candidates.append((distance, beat_interval))
        if not candidates:
            self._intervals_ns.clear()
            self._stable_bpm = None
            return None
        _, normalized_interval = min(candidates)
        self._intervals_ns.append(normalized_interval)
        if len(self._intervals_ns) < 3:
            return None
        median_interval = statistics.median(self._intervals_ns)
        inliers = [
            sample
            for sample in self._intervals_ns
            if abs(sample - median_interval) / median_interval <= 0.12
        ]
        if len(inliers) < 3:
            return None
        measured_bpm = round(60_000_000_000 / statistics.median(inliers))
        if self._stable_bpm is None:
            self._stable_bpm = measured_bpm
        else:
            difference = measured_bpm - self._stable_bpm
            if abs(difference) <= 2:
                return self._stable_bpm
            step = max(-3, min(3, difference))
            self._stable_bpm += step
        return self._stable_bpm


def style_rhythm_spans(
    style_id: str, phrase_bars: int | None = None
) -> tuple[float, ...]:
    """Return plausible beat gaps between bass and chord attacks for a style."""

    renderer = DEMO_STYLES[style_id].renderer
    measure_count = phrase_bars or len(renderer._GROOVE)
    grooves = renderer._GROOVE[:measure_count]
    phrase_beats = len(grooves) * renderer.BEATS_PER_BAR
    positions = sorted(
        {
            (bar * renderer.BEATS_PER_BAR) + onset
            for bar, groove in enumerate(grooves)
            for onset in (*groove.bass_onsets, *groove.chord_onsets)
        }
    )
    gaps = {
        round(later - earlier, 3)
        for earlier, later in pairwise(positions)
        if later > earlier
    }
    if positions:
        wrap = phrase_beats - positions[-1] + positions[0]
        if wrap > 0:
            gaps.add(round(wrap, 3))
    gaps.update(renderer.SYNCOPATION_GROUPS)
    gaps.update((2.0, renderer.BEATS_PER_BAR))
    return tuple(sorted(gap for gap in gaps if gap >= 0.25))


class ArrangerAudio(Protocol):
    """Audio boundary used by the deterministic state-machine tests."""

    @property
    def section(self) -> DemoSection:
        """Return the current rendered section."""

    @property
    def position_ticks(self) -> int | None:
        """Return the rendered transport position in integer quarter-note ticks."""

    @property
    def fill_variation(self) -> int | None:
        """Return the queued or currently sounding fill variation."""

    def select_style(
        self,
        style_id: str,
        custom_style: CustomStyle | None = None,
        imported_style: Style | None = None,
    ) -> None: ...

    def configure_style_controls(self, controls: StyleControls) -> None: ...

    def set_tempo(self, tempo_bpm: int) -> None: ...

    def set_chord(self, chord: ChordState | None) -> None: ...

    def start_main(self) -> None: ...

    def start_intro(self) -> None: ...

    def request_ending(self) -> None: ...

    def request_fill(self, variation: int) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...

    def configure_output(self, device: str | None) -> None: ...


class ProceduralArrangerAudio:
    """Lazily open the selected PCM route and own the accompaniment worker."""

    def __init__(
        self,
        *,
        sink_factory: Callable[[DemoAudioConfig, str], PcmSink] | None = None,
        soundfont_path: str | None = None,
        soundfont_name: str | None = None,
        sfz_waltz_paths: SfzWaltzPaths | None = None,
        sfz_style_paths: SfzStylePaths | None = None,
    ) -> None:
        first_style = next(iter(DEMO_STYLES.values()))
        self._style_id = first_style.id
        self._custom_style: CustomStyle | None = None
        self._imported_style: Style | None = None
        self._tempo_bpm = first_style.default_tempo_bpm
        self._chord: ChordState | None = None
        self._sink_factory = sink_factory or (
            lambda config, device: open_pcm_sink(config, device)
        )
        self._soundfont_path = soundfont_path or os.environ.get("OSTINATO_SOUNDFONT")
        self._soundfont_name = soundfont_name or os.environ.get(
            "OSTINATO_SOUNDFONT_NAME", "configured SoundFont"
        )
        self._sfz_style_paths = sfz_style_paths or SfzStylePaths.from_environment()
        self._sfz_waltz_paths = (
            sfz_waltz_paths
            or (
                self._sfz_style_paths.waltz
                if self._sfz_style_paths is not None
                else None
            )
            or SfzWaltzPaths.from_environment()
        )
        self._device: str | None = None
        self._session: RealtimeDemoArranger | None = None
        self._style_controls = StyleControls()

    def configure_output(self, device: str | None) -> None:
        """Select an exact discovered route, closing an idle prior stream."""

        if device == self._device and (
            self._session is None or self._session.error is None
        ):
            return
        if self._session is not None:
            with suppress(AudioPlaybackError):
                self._session.close()
            self._session = None
        self._device = device

    @property
    def section(self) -> DemoSection:
        if self._session is None:
            return DemoSection.STOPPED
        return self._session.section

    @property
    def position_ticks(self) -> int | None:
        if self._session is None:
            return None
        return self._session.position_ticks

    @property
    def fill_variation(self) -> int | None:
        if self._session is None:
            return None
        return self._session.fill_variation

    @property
    def error(self) -> str | None:
        """Expose an asynchronous ALSA worker failure to arranger status."""

        return self._session.error if self._session is not None else None

    @property
    def synthesis_engine(self) -> str:
        """Describe the active renderer without exposing a machine path."""

        if (
            self._style_id == "classic_waltz"
            and self._custom_style is None
            and self._sfz_waltz_paths is not None
        ):
            return "sfizz · open sampled orchestra"
        if self._imported_style is not None and self._soundfont_path:
            return f"FluidSynth · {self._soundfont_name}"
        if self._custom_style is None and self._sfz_style_paths is not None:
            return "sfizz · open sampled genre ensemble"
        if self._soundfont_path:
            return f"FluidSynth · {self._soundfont_name}"
        return "procedural PCM"

    def select_style(
        self,
        style_id: str,
        custom_style: CustomStyle | None = None,
        imported_style: Style | None = None,
    ) -> None:
        if imported_style is None and style_id not in DEMO_STYLES:
            raise ArrangerError(f"unknown arranger style: {style_id}")
        if custom_style is not None and imported_style is not None:
            raise ArrangerError("a style cannot be both custom and imported")
        if (
            custom_style is not None or imported_style is not None
        ) and self._soundfont_path is None:
            raise ArrangerError(
                "custom and imported styles require a configured SoundFont"
            )
        if imported_style is not None:
            imported_style_playback_info(imported_style)
        if self._session is not None:
            with suppress(AudioPlaybackError):
                self._session.close()
            self._session = None
        self._style_id = style_id
        self._custom_style = custom_style
        self._imported_style = imported_style

    def configure_style_controls(self, controls: StyleControls) -> None:
        self._style_controls = controls
        if self._session is not None:
            self._session.configure_style_controls(controls)

    @property
    def main_variation(self) -> int:
        return (
            self._session.main_variation
            if self._session
            else self._style_controls.variation
        )

    @property
    def pattern_state(self) -> tuple[str, int] | None:
        return self._session.pattern_state if self._session else None

    def set_tempo(self, tempo_bpm: int) -> None:
        self._tempo_bpm = tempo_bpm
        if self._session is not None:
            self._session.set_tempo(tempo_bpm)

    def set_chord(self, chord: ChordState | None) -> None:
        self._chord = chord
        if self._session is not None:
            self._session.set_chord(chord)

    def start_main(self) -> None:
        session = self._ensure_session()
        session.set_chord(self._chord)
        session.start_main()

    def start_intro(self) -> None:
        session = self._ensure_session()
        session.set_chord(self._chord)
        session.start_intro()

    def request_ending(self) -> None:
        if self._session is not None:
            self._session.request_ending()

    def request_fill(self, variation: int) -> None:
        if self._session is not None:
            self._session.request_fill(variation)

    def stop(self) -> None:
        if self._session is not None:
            self._session.stop_playback()

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    def _ensure_session(self) -> RealtimeDemoArranger:
        if self._session is None:
            if self._device is None:
                raise ArrangerError("select an accompaniment audio output first")
            config = DemoAudioConfig(tempo_bpm=self._tempo_bpm)
            try:
                sink = self._sink_factory(config, self._device)
            except Exception as error:
                raise ArrangerError(
                    f"could not open accompaniment audio: {error}"
                ) from error
            if self._imported_style is not None and self._soundfont_path:
                imported_style = self._imported_style
                soundfont_path = self._soundfont_path

                def imported_renderer_factory(
                    _style_id: str, renderer_config: DemoAudioConfig
                ) -> ImportedStyleArrangementRenderer:
                    return ImportedStyleArrangementRenderer(
                        imported_style, renderer_config, soundfont_path
                    )

                self._session = RealtimeDemoArranger(
                    config,
                    sink,
                    style_id=self._style_id,
                    renderer_factory=imported_renderer_factory,
                )
            elif (
                self._style_id == "classic_waltz"
                and self._custom_style is None
                and self._sfz_waltz_paths is not None
            ):
                sfz_waltz_paths = self._sfz_waltz_paths

                def sfz_renderer_factory(
                    style_id: str, renderer_config: DemoAudioConfig
                ) -> SfzWaltzArrangementRenderer:
                    if style_id != "classic_waltz":
                        raise ArrangerError(
                            "the open SFZ orchestra is available only for Classic Waltz"
                        )
                    return SfzWaltzArrangementRenderer(renderer_config, sfz_waltz_paths)

                self._session = RealtimeDemoArranger(
                    config,
                    sink,
                    style_id=self._style_id,
                    renderer_factory=sfz_renderer_factory,
                )
            elif self._custom_style is None and self._sfz_style_paths is not None:
                sfz_style_paths = self._sfz_style_paths

                def sfz_style_renderer_factory(
                    style_id: str, renderer_config: DemoAudioConfig
                ) -> SfzStyleArrangementRenderer:
                    return SfzStyleArrangementRenderer(
                        style_id, renderer_config, sfz_style_paths
                    )

                self._session = RealtimeDemoArranger(
                    config,
                    sink,
                    style_id=self._style_id,
                    renderer_factory=sfz_style_renderer_factory,
                )
            elif self._soundfont_path:
                soundfont_path = self._soundfont_path

                def soundfont_renderer_factory(
                    style_id: str, renderer_config: DemoAudioConfig
                ) -> SoundFontArrangementRenderer:
                    return SoundFontArrangementRenderer(
                        style_id,
                        renderer_config,
                        soundfont_path,
                        custom_style=self._custom_style,
                    )

                self._session = RealtimeDemoArranger(
                    config,
                    sink,
                    style_id=self._style_id,
                    renderer_factory=soundfont_renderer_factory,
                )
            else:
                self._session = RealtimeDemoArranger(
                    config,
                    sink,
                    style_id=self._style_id,
                )
            self._session.configure_style_controls(self._style_controls)
            self._session.set_chord(self._chord)
            self._session.start()
        return self._session


class LiveArrangerService:
    """Apply saved MIDI roles and UI commands to backend-owned arranger state."""

    def __init__(
        self,
        audio: ArrangerAudio | None = None,
        *,
        clock: Callable[[], int] = time.monotonic_ns,
        chord_coalesce_ns: int = CHORD_COALESCE_NS,
    ) -> None:
        if chord_coalesce_ns <= 0:
            raise ValueError("chord_coalesce_ns must be positive")
        first_style = next(iter(DEMO_STYLES.values()))
        self._audio = audio or ProceduralArrangerAudio()
        self._style_controls = StyleControls()
        self._custom_styles: dict[str, CustomStyle] = {}
        self._imported_styles: dict[str, Style] = {}
        self._clock = clock
        self._style_id = first_style.id
        self._tempo_bpm = first_style.default_tempo_bpm
        self._tempo_source = "style default"
        self._tempo_mode = TEMPO_MODE_AUTO
        self._rhythm_tracker = BassTempoTracker()
        self._auto_tempo_sources: set[str] = set()
        self._chord_coalesce_ns = chord_coalesce_ns
        self._chord_max_coalesce_ns = max(CHORD_MAX_COALESCE_NS, chord_coalesce_ns)
        self._treble_channel: int | None = None
        self._bass_channel: int | None = None
        self._chord_channel: int | None = None
        self._active_melody_notes: set[int] = set()
        self._recent_melody_notes: deque[int] = deque(maxlen=RECENT_MELODY_NOTE_COUNT)
        self._active_chord_notes: set[int] = set()
        self._pending_chord_notes: set[int] = set()
        self._chord_started_at_ns: int | None = None
        self._chord_dirty_at_ns: int | None = None
        self._last_bass_pitch_class: int | None = None
        self._chord: ChordState | None = None
        self._confirmed_chord: ChordState | None = None
        self._prediction_bass_pitch_class: int | None = None
        self._harmony_source: str | None = None
        self._prediction_confidence: float | None = None
        self._running = False
        self._intro_armed = False
        self._sync_enabled = False
        self._sync_stop_at_ns: int | None = None
        self._error: str | None = None
        self._output_configured = False
        self._style_previewing = False
        self._preview_tempo_bpm: int | None = None
        self._preview_stop_at_ns: int | None = None
        self._audio.select_style(self._style_id)
        self._audio.set_tempo(self._tempo_bpm)

    def configure_custom_styles(self, styles: Sequence[CustomStyle]) -> None:
        """Replace the saved user-style catalog while transport is stopped."""

        if self._running:
            raise ArrangerError("stop the arranger before changing custom styles")
        self._stop_style_preview()
        collisions = {style.id for style in styles} & (
            set(DEMO_STYLES) | set(self._imported_styles)
        )
        if collisions:
            raise ArrangerError(
                f"duplicate arranger style identifier: {sorted(collisions)[0]}"
            )
        self._custom_styles = {style.id: style for style in styles}
        if self._style_id in DEMO_STYLES or self._style_id in self._imported_styles:
            return
        selected = self._custom_styles.get(self._style_id)
        if selected is None:
            self._select_style(next(iter(DEMO_STYLES)))
            return
        self._apply_style_selection(selected.id, selected)

    def configure_imported_styles(self, styles: Sequence[Style]) -> None:
        """Replace the read-only local import catalog while transport is stopped."""

        if self._running:
            raise ArrangerError("stop the arranger before changing imported styles")
        validated: dict[str, Style] = {}
        reserved = set(DEMO_STYLES) | set(self._custom_styles)
        for style in styles:
            imported_style_playback_info(style)
            if style.id in reserved or style.id in validated:
                raise ArrangerError(f"duplicate arranger style identifier: {style.id}")
            validated[style.id] = style
        self._imported_styles = validated
        if self._style_id in DEMO_STYLES or self._style_id in self._custom_styles:
            return
        selected = self._imported_styles.get(self._style_id)
        if selected is None:
            self._select_style(next(iter(DEMO_STYLES)))
            return
        self._apply_style_selection(selected.id, None, selected)

    def configure_profile(self, profile: Mapping[str, object] | None) -> None:
        """Use only reviewed treble/bass/chord channels from the saved profile."""

        self._treble_channel = self._profile_channel(profile, "treble")
        self._bass_channel = self._profile_channel(profile, "bass")
        self._chord_channel = self._profile_channel(profile, "chord")
        self._active_melody_notes.clear()
        self._recent_melody_notes.clear()
        self._active_chord_notes.clear()
        self._pending_chord_notes.clear()
        self._chord_started_at_ns = None
        self._chord_dirty_at_ns = None
        self._last_bass_pitch_class = None
        self._prediction_bass_pitch_class = None
        self._prediction_confidence = None
        self._reset_auto_tempo()

    def configure_audio_output(self, device: str | None) -> None:
        """Apply an exact ALSA PCM identifier selected from current discovery."""

        if self._running:
            raise ArrangerError("stop the arranger before changing audio output")
        self._stop_style_preview()
        self._audio.configure_output(device)
        self._output_configured = device is not None
        self._error = None

    def command(self, action: str, value: object | None = None) -> JsonObject:
        """Apply one validated web control and return the resulting snapshot."""

        try:
            self._stop_style_preview()
            if action == "style":
                self._select_style(value)
            elif action in {
                "variation",
                "intro_select",
                "ending_select",
                "track_mix",
                "mix_reset",
            }:
                self._configure_style_controls(action, value)
            elif action == "start":
                self._start(intro=False)
            elif action == "stop":
                self._stop()
            elif action == "intro":
                if self._sync_enabled and not self._running:
                    self._intro_armed = True
                else:
                    self._start(intro=True)
            elif action == "ending":
                if self._running:
                    self._audio.request_ending()
            elif action == "fill":
                if type(value) is not int or value not in (1, 2):
                    raise ArrangerError("fill command requires variation 1 or 2")
                if not self._running or self._audio.section is not DemoSection.MAIN:
                    raise ArrangerError(
                        "fill-ins are available while the main style is playing"
                    )
                self._audio.request_fill(value)
            elif action == "sync":
                if not isinstance(value, bool):
                    raise ArrangerError("sync command requires a boolean value")
                self._sync_enabled = value
                self._sync_stop_at_ns = None
            elif action == "tempo_mode":
                self._set_tempo_mode(value)
            elif action == "tempo":
                self._set_fixed_tempo(value)
            elif action == "panic":
                self._chord = None
                self._confirmed_chord = None
                self._prediction_bass_pitch_class = None
                self._harmony_source = None
                self._prediction_confidence = None
                self._audio.set_chord(None)
                self._stop()
            else:
                raise ArrangerError(f"unknown arranger command: {action}")
            self._error = None
        except ArrangerError:
            raise
        except Exception as error:
            self._error = str(error)
            self._running = False
            raise ArrangerError(str(error)) from error
        return self.snapshot()

    def trigger_performance_control(self, action: PerformanceControlAction) -> bool:
        """Apply one learned physical control without disrupting MIDI monitoring."""

        command: str = action
        value: object | None = None
        if action == "fill_1":
            command = "fill"
            value = 1
        elif action == "fill_2":
            command = "fill"
            value = 2
        try:
            if action.startswith("variation_"):
                command, value = "variation", int(action[-1])
            elif action.startswith(("intro_", "ending_")):
                command = action.rsplit("_", 1)[0]
                self.command(f"{command}_select", int(action[-1]))
            self.command(command, value)
        except ArrangerError:
            return False
        return True

    def handle_midi_event(self, event: Mapping[str, object]) -> None:
        """Consume one raw input event without assigning unsaved channels."""

        if event.get("type") != "midi" or event.get("direction") != "in":
            return
        if self._style_previewing:
            return
        channel = event.get("channel")
        note = event.get("note")
        timestamp_ns = event.get("timestamp_ns")
        if not all(type(item) is int for item in (channel, note, timestamp_ns)):
            return
        channel_value = cast(int, channel)
        note_value = cast(int, note)
        timestamp_value = cast(int, timestamp_ns)
        message_type = event.get("message_type")
        velocity = event.get("velocity")
        active = message_type == "note_on" and type(velocity) is int and velocity > 0
        released = message_type == "note_off" or (
            message_type == "note_on" and velocity == 0
        )
        if channel_value == self._bass_channel and active:
            self._last_bass_pitch_class = note_value % 12
            self._apply_harmony_prediction(note_value % 12, timestamp_value)
            self._observe_left_hand_pulse(timestamp_value, "bass")
            self._register_sync_activity(timestamp_value)
        if channel_value == self._treble_channel and channel_value not in {
            self._bass_channel,
            self._chord_channel,
        }:
            if active:
                self._active_melody_notes.add(note_value)
                self._recent_melody_notes.append(note_value)
                if (
                    self._prediction_bass_pitch_class is not None
                    and self._chord_dirty_at_ns is None
                ):
                    self._apply_harmony_prediction(
                        self._prediction_bass_pitch_class, timestamp_value
                    )
            elif released:
                self._active_melody_notes.discard(note_value)
        if channel_value == self._chord_channel:
            if active:
                self._resolve_chord_cluster(timestamp_value)
                if self._chord_dirty_at_ns is None:
                    self._pending_chord_notes.clear()
                    self._chord_started_at_ns = timestamp_value
                    self._chord_dirty_at_ns = timestamp_value
                    self._observe_left_hand_pulse(timestamp_value, "chords")
                else:
                    self._chord_dirty_at_ns = timestamp_value
                self._active_chord_notes.add(note_value)
                self._pending_chord_notes.add(note_value)
                self._register_sync_activity(timestamp_value)
            elif released:
                self._active_chord_notes.discard(note_value)

    def advance(self, now_ns: int | None = None) -> JsonObject:
        """Resolve due chord clusters, sync stop, and completed endings."""

        now = self._clock() if now_ns is None else now_ns
        audio_error = getattr(self._audio, "error", None)
        if isinstance(audio_error, str):
            self._error = audio_error
            self._running = False
            self._style_previewing = False
            self._preview_tempo_bpm = None
            self._preview_stop_at_ns = None
        self._resolve_chord_cluster(now)
        if (
            self._running
            and self._sync_enabled
            and self._sync_stop_at_ns is not None
            and now >= self._sync_stop_at_ns
        ):
            self._stop()
        if self._running and self._audio.section is DemoSection.STOPPED:
            self._running = False
            self._sync_stop_at_ns = None
        if (
            self._style_previewing
            and self._preview_stop_at_ns is not None
            and now >= self._preview_stop_at_ns
        ):
            self._stop_style_preview()
        return self.snapshot()

    def next_check_delay_seconds(
        self,
        *,
        now_ns: int | None = None,
        idle_seconds: float = 0.05,
    ) -> float:
        """Return an event-loop wait bounded by the next arranger deadline."""

        if idle_seconds <= 0:
            raise ValueError("idle_seconds must be positive")
        now = self._clock() if now_ns is None else now_ns
        deadlines: list[int] = []
        chord_deadline = self._chord_deadline_ns()
        if chord_deadline is not None:
            deadlines.append(chord_deadline)
        if self._running and self._sync_stop_at_ns is not None:
            deadlines.append(self._sync_stop_at_ns)
        if self._style_previewing and self._preview_stop_at_ns is not None:
            deadlines.append(self._preview_stop_at_ns)
        if not deadlines:
            return idle_seconds
        remaining_seconds = max(0, min(deadlines) - now) / 1_000_000_000
        return min(idle_seconds, remaining_seconds)

    def snapshot(self) -> JsonObject:
        """Return browser-safe arranger status and the complete style catalog."""

        definition = self._current_definition()
        custom_style = self._custom_styles.get(self._style_id)
        imported_style = self._imported_styles.get(self._style_id)
        beats_per_bar = self._current_beats_per_bar()
        section = self._audio.section.value if self._running else "stopped"
        position_ticks = self._audio.position_ticks if self._running else None
        beat_index = (
            (position_ticks // TRANSPORT_TICKS_PER_BEAT) % beats_per_bar
            if position_ticks is not None
            else None
        )
        if self._intro_armed and not self._running:
            section = "intro_armed"
        return {
            "type": "arranger.status",
            "style": self._style_id,
            "styles": [
                {
                    "id": style.id,
                    "name": style.name,
                    "description": style.description,
                    "default_tempo_bpm": style.default_tempo_bpm,
                    "beats_per_bar": style.beats_per_bar,
                    "provenance": style.provenance,
                    "custom": False,
                    "group": musical_style_group(style.name),
                }
                for style in DEMO_STYLES.values()
            ]
            + [
                {
                    "id": style.id,
                    "name": style.name,
                    "description": (
                        f"Custom {style.beats_per_bar}/4 · {style.phrase_bars} "
                        f"measure phrase · {DEMO_STYLES[style.base_style_id].name}"
                    ),
                    "default_tempo_bpm": style.tempo_bpm,
                    "beats_per_bar": style.beats_per_bar,
                    "phrase_bars": style.phrase_bars,
                    "custom": True,
                    "group": CUSTOM_STYLE_GROUP,
                }
                for style in self._custom_styles.values()
            ]
            + [
                {
                    "id": style.id,
                    "name": style.name,
                    "description": (
                        "Sampled accompaniment · Ostinato chord adaptation"
                    ),
                    "default_tempo_bpm": self._imported_default_tempo(style),
                    "beats_per_bar": imported_style_playback_info(style).beats_per_bar,
                    "provenance": (
                        f"{style.source.manufacturer} {style.source.source_format} · "
                        f"{style.source.original_file}"
                    ),
                    "custom": False,
                    "imported": True,
                    "group": imported_style_group(style),
                }
                for style in self._imported_styles.values()
            ],
            "tempo_bpm": self._tempo_bpm,
            "tempo_source": self._tempo_source,
            "tempo_mode": self._tempo_mode,
            "beats_per_bar": (
                custom_style.beats_per_bar
                if custom_style is not None
                else (
                    imported_style_playback_info(imported_style).beats_per_bar
                    if imported_style is not None
                    else definition.beats_per_bar
                )
            ),
            "ticks_per_beat": TRANSPORT_TICKS_PER_BEAT,
            "position_ticks": position_ticks,
            "beat_index": beat_index,
            "running": self._running,
            "section": section,
            "fill_variation": (self._audio.fill_variation if self._running else None),
            "style_controls": self._style_control_snapshot(imported_style),
            "sync_enabled": self._sync_enabled,
            "sync_stop_bars": SYNC_STOP_BARS,
            "chord": self._harmony_name(),
            "harmony_source": self._harmony_source,
            "prediction_confidence": self._prediction_confidence,
            "bass": (
                PITCH_CLASS_NAMES[self._last_bass_pitch_class]
                if self._last_bass_pitch_class is not None
                else None
            ),
            "bass_channel": self._bass_channel,
            "chord_channel": self._chord_channel,
            "output_mode": "host_analog_audio",
            "synthesis_engine": getattr(
                self._audio, "synthesis_engine", "procedural PCM"
            ),
            "output_configured": self._output_configured,
            "style_previewing": self._style_previewing,
            "preview_tempo_bpm": self._preview_tempo_bpm,
            "preview_duration_seconds": STYLE_PREVIEW_DURATION_NS // 1_000_000_000,
            "error": self._error or getattr(self._audio, "error", None),
        }

    def preview_custom_style(self, style: CustomStyle, tempo_bpm: int) -> JsonObject:
        """Render an unsaved style against C major without changing selection."""

        if self._running:
            raise ArrangerError("stop the arranger before previewing a style")
        if not self._output_configured:
            raise ArrangerError("select an accompaniment audio output first")
        if not MIN_TEMPO_BPM <= tempo_bpm <= MAX_TEMPO_BPM:
            raise ArrangerError(
                f"preview tempo must be between {MIN_TEMPO_BPM} and {MAX_TEMPO_BPM} BPM"
            )
        self._stop_style_preview()
        try:
            self._audio.select_style(style.base_style_id, style)
            self._audio.set_tempo(tempo_bpm)
            self._audio.set_chord(
                ChordState(
                    root_pitch_class=0,
                    quality=ChordQuality.MAJOR,
                    bass_pitch_class=0,
                    confidence=1.0,
                    source_event_ids=("style-preview",),
                    recognized_at_ns=self._clock(),
                )
            )
            self._audio.start_main()
        except Exception as error:
            self._restore_selected_audio()
            raise ArrangerError(str(error)) from error
        self._style_previewing = True
        self._preview_tempo_bpm = tempo_bpm
        self._preview_stop_at_ns = self._clock() + STYLE_PREVIEW_DURATION_NS
        self._error = None
        return self.snapshot()

    def stop_style_preview(self) -> JsonObject:
        """Stop a designer preview and restore the selected live arrangement."""

        self._stop_style_preview()
        return self.snapshot()

    def close(self) -> None:
        """Stop accompaniment and release the audio process."""

        self._audio.close()

    def _stop_style_preview(self) -> None:
        if not self._style_previewing:
            return
        self._audio.stop()
        self._style_previewing = False
        self._preview_tempo_bpm = None
        self._preview_stop_at_ns = None
        self._restore_selected_audio()

    def _restore_selected_audio(self) -> None:
        custom_style = self._custom_styles.get(self._style_id)
        imported_style = self._imported_styles.get(self._style_id)
        base_style_id = (
            custom_style.base_style_id if custom_style is not None else self._style_id
        )
        self._audio.select_style(base_style_id, custom_style, imported_style)
        if imported_style is not None:
            self._audio.configure_style_controls(self._style_controls)
        self._audio.set_tempo(self._tempo_bpm)
        self._audio.set_chord(self._chord)

    def _select_style(self, value: object | None) -> None:
        if not isinstance(value, str):
            raise ArrangerError(f"unknown arranger style: {value}")
        if self._running:
            raise ArrangerError("stop the arranger before changing style")
        custom_style = self._custom_styles.get(value)
        imported_style = self._imported_styles.get(value)
        if value not in DEMO_STYLES and custom_style is None and imported_style is None:
            raise ArrangerError(f"unknown arranger style: {value}")
        self._apply_style_selection(value, custom_style, imported_style)

    def _apply_style_selection(
        self,
        value: str,
        custom_style: CustomStyle | None,
        imported_style: Style | None = None,
    ) -> None:
        base_style_id = (
            custom_style.base_style_id if custom_style is not None else value
        )
        self._style_id = value
        self._reset_auto_tempo()
        if self._tempo_mode == TEMPO_MODE_AUTO:
            self._tempo_bpm = (
                custom_style.tempo_bpm
                if custom_style is not None
                else (
                    self._imported_default_tempo(imported_style)
                    if imported_style is not None
                    else DEMO_STYLES[base_style_id].default_tempo_bpm
                )
            )
            self._tempo_source = "style default"
        self._intro_armed = False
        self._audio.select_style(base_style_id, custom_style, imported_style)
        self._style_controls = StyleControls()
        if imported_style is not None:
            self._audio.configure_style_controls(self._style_controls)
        self._audio.set_tempo(self._tempo_bpm)

    def _configure_style_controls(self, action: str, value: object) -> None:
        style = self._imported_styles.get(self._style_id)
        if style is None:
            raise ArrangerError(
                "section selection and track mix require an imported style"
            )
        info = imported_style_playback_info(style)
        controls = self._style_controls
        if action == "mix_reset":
            controls = replace(controls, tracks=())
        elif action == "track_mix":
            try:
                controls = controls.update_track(value)
            except ValueError as error:
                raise ArrangerError(str(error)) from error
            roles = {
                track.role
                for pattern in info.sections.values()
                for track in pattern.tracks
            }
            if any(track.role not in roles for track in controls.tracks):
                raise ArrangerError("this style does not contain that track")
        else:
            kind = action.removesuffix("_select")
            if type(value) is not int or f"{kind}_{value}" not in info.sections:
                raise ArrangerError(f"this style has no {kind} {value}")
            if kind == "variation":
                controls = replace(controls, variation=value)
            elif kind == "intro":
                controls = replace(controls, intro=value)
            else:
                controls = replace(controls, ending=value)
        self._audio.configure_style_controls(controls)
        self._style_controls = controls

    def _style_control_snapshot(self, style: Style | None) -> JsonObject | None:
        if style is None:
            return None
        info = imported_style_playback_info(style)
        choices = {
            kind: sorted(
                int(name.rsplit("_", 1)[1])
                for name in info.sections
                if name.startswith(kind + "_")
            )
            for kind in ("variation", "intro", "ending", "fill")
        }
        roles = {
            track.role for pattern in info.sections.values() for track in pattern.tracks
        }
        controls = self._style_controls
        pattern_state = (
            getattr(self._audio, "pattern_state", None) if self._running else None
        )
        return {
            "available": choices,
            "active_section": pattern_state[0]
            if pattern_state
            else f"variation_{controls.variation}",
            "pattern_origin_ticks": pattern_state[1] if pattern_state else 0,
            "variation": controls.variation,
            "active_variation": getattr(
                self._audio, "main_variation", controls.variation
            )
            if self._running
            else controls.variation,
            "intro": controls.intro,
            "ending": controls.ending,
            "tracks": [
                {
                    "role": role.value,
                    "name": "Accompaniment " + role.value[-1]
                    if role.value.startswith("acc")
                    else role.value.title(),
                    "volume": controls.track(role).volume,
                    "muted": controls.track(role).muted,
                    "solo": controls.track(role).solo,
                    "audible": controls.audible(role),
                }
                for role in StyleTrackRole
                if role in roles
            ],
            "source_patterns": {
                element.type.value: [cv.number for cv in element.chord_variations]
                for element in style.elements
            },
        }

    def _current_definition(self) -> DemoStyleDefinition:
        custom_style = self._custom_styles.get(self._style_id)
        style_id = (
            custom_style.base_style_id if custom_style is not None else self._style_id
        )
        return DEMO_STYLES.get(style_id, next(iter(DEMO_STYLES.values())))

    def _current_beats_per_bar(self) -> int:
        custom_style = self._custom_styles.get(self._style_id)
        if custom_style is not None:
            return custom_style.beats_per_bar
        imported_style = self._imported_styles.get(self._style_id)
        if imported_style is not None:
            return imported_style_playback_info(imported_style).beats_per_bar
        return self._current_definition().beats_per_bar

    @staticmethod
    def _imported_default_tempo(style: Style | None) -> int:
        if style is None or style.tempo_bpm is None:
            return 120
        return max(MIN_TEMPO_BPM, min(MAX_TEMPO_BPM, round(style.tempo_bpm)))

    def _set_tempo_mode(self, value: object | None) -> None:
        if value not in (TEMPO_MODE_AUTO, TEMPO_MODE_FIXED):
            raise ArrangerError(f"unknown tempo mode: {value}")
        self._tempo_mode = cast(str, value)
        self._reset_auto_tempo()
        self._tempo_source = (
            "fixed control"
            if self._tempo_mode == TEMPO_MODE_FIXED
            else "left-hand auto · waiting for bass or chord"
        )

    def _set_fixed_tempo(self, value: object | None) -> None:
        if type(value) is not int or not MIN_TEMPO_BPM <= value <= MAX_TEMPO_BPM:
            raise ArrangerError(
                f"fixed tempo must be between {MIN_TEMPO_BPM} and {MAX_TEMPO_BPM} BPM"
            )
        self._tempo_mode = TEMPO_MODE_FIXED
        self._tempo_bpm = value
        self._tempo_source = "fixed control"
        self._reset_auto_tempo()
        self._audio.set_tempo(self._tempo_bpm)

    def _start(self, *, intro: bool) -> None:
        if not self._output_configured:
            raise ArrangerError("select an accompaniment audio output first")
        if intro or self._intro_armed:
            self._audio.start_intro()
        else:
            self._audio.start_main()
        self._running = True
        self._intro_armed = False
        if self._sync_enabled:
            self._arm_sync_stop(self._clock())

    def _stop(self) -> None:
        self._audio.stop()
        self._running = False
        self._sync_stop_at_ns = None

    def _observe_left_hand_pulse(self, timestamp_ns: int, source: str) -> None:
        if self._tempo_mode != TEMPO_MODE_AUTO:
            return
        self._auto_tempo_sources.add(source)
        custom_style = self._custom_styles.get(self._style_id)
        imported_style = self._imported_styles.get(self._style_id)
        tempo = self._rhythm_tracker.observe(
            timestamp_ns,
            beat_spans=(
                imported_style_rhythm_spans(
                    imported_style,
                    variation_number=getattr(
                        self._audio, "main_variation", self._style_controls.variation
                    ),
                )
                if imported_style is not None
                else style_rhythm_spans(
                    self._current_definition().id,
                    custom_style.phrase_bars if custom_style is not None else None,
                )
            ),
            reference_bpm=self._tempo_bpm,
        )
        if tempo is not None or self._tempo_source.startswith("left hand ·"):
            self._tempo_source = self._automatic_tempo_source()
        if tempo is None:
            return
        if tempo != self._tempo_bpm:
            self._tempo_bpm = tempo
            self._audio.set_tempo(tempo)

    def _resolve_chord_cluster(self, now_ns: int) -> None:
        started_at = self._chord_started_at_ns
        deadline = self._chord_deadline_ns()
        if started_at is None or deadline is None or now_ns < deadline:
            return
        notes = sorted(self._pending_chord_notes)
        self._chord_started_at_ns = None
        self._chord_dirty_at_ns = None
        self._pending_chord_notes.clear()
        recognized = classify_chord_notes(notes)
        if recognized is None:
            return
        chord = ChordState(
            root_pitch_class=recognized.root_pitch_class,
            quality=recognized.quality,
            bass_pitch_class=None,
            confidence=1.0,
            source_event_ids=(f"live-{recognized.transmission}-{started_at}",),
            recognized_at_ns=now_ns,
        )
        self._chord = chord
        self._confirmed_chord = chord
        self._prediction_bass_pitch_class = None
        self._harmony_source = "chord button"
        self._prediction_confidence = None
        self._audio.set_chord(chord)

    def _chord_deadline_ns(self) -> int | None:
        started_at = self._chord_started_at_ns
        dirty_at = self._chord_dirty_at_ns
        if started_at is None or dirty_at is None:
            return None
        return min(
            dirty_at + self._chord_coalesce_ns,
            started_at + self._chord_max_coalesce_ns,
        )

    def _apply_harmony_prediction(
        self, bass_pitch_class: int, timestamp_ns: int
    ) -> None:
        prediction = predict_harmony(
            bass_pitch_class,
            self._confirmed_chord,
            active_melody_notes=tuple(self._active_melody_notes),
            recent_melody_notes=tuple(self._recent_melody_notes),
            harmonic_boundary=self._at_harmonic_boundary(),
        )
        chord = ChordState(
            root_pitch_class=prediction.root_pitch_class,
            quality=prediction.quality,
            bass_pitch_class=None,
            confidence=prediction.confidence,
            source_event_ids=(f"predicted-bass-melody-{timestamp_ns}",),
            recognized_at_ns=timestamp_ns,
        )
        self._chord = chord
        self._prediction_bass_pitch_class = bass_pitch_class
        self._harmony_source = "bass + melody prediction"
        self._prediction_confidence = prediction.confidence
        self._audio.set_chord(chord)

    def _at_harmonic_boundary(self) -> bool:
        if not self._running:
            return True
        position_ticks = self._audio.position_ticks
        if position_ticks is None:
            return True
        bar_ticks = self._current_beats_per_bar() * TRANSPORT_TICKS_PER_BEAT
        position_in_bar = position_ticks % bar_ticks
        return (
            position_in_bar <= TRANSPORT_TICKS_PER_BEAT // 3
            or bar_ticks - position_in_bar <= TRANSPORT_TICKS_PER_BEAT // 8
        )

    def _reset_auto_tempo(self) -> None:
        self._rhythm_tracker.reset()
        self._auto_tempo_sources.clear()

    def _automatic_tempo_source(self) -> str:
        if self._auto_tempo_sources == {"bass", "chords"}:
            return "left hand · bass + chords"
        if "chords" in self._auto_tempo_sources:
            return "left hand · chords"
        return "left hand · bass"

    def _harmony_name(self) -> str | None:
        if self._chord is None:
            return None
        name = self._chord.name
        bass = self._chord.bass_pitch_class
        if bass is None or bass == self._chord.root_pitch_class:
            return name
        return f"{name}/{PITCH_CLASS_NAMES[bass]}"

    def _register_sync_activity(self, timestamp_ns: int) -> None:
        if not self._sync_enabled:
            return
        if not self._running:
            self._start(intro=self._intro_armed)
        self._arm_sync_stop(timestamp_ns)

    def _arm_sync_stop(self, timestamp_ns: int) -> None:
        duration_ns = round(
            SYNC_STOP_BARS
            * self._current_beats_per_bar()
            * 60_000_000_000
            / self._tempo_bpm
        )
        self._sync_stop_at_ns = timestamp_ns + duration_ns

    @staticmethod
    def _profile_channel(profile: Mapping[str, object] | None, role: str) -> int | None:
        if profile is None:
            return None
        roles = profile.get("roles")
        if not isinstance(roles, Mapping):
            return None
        result = roles.get(role)
        if not isinstance(result, Mapping):
            return None
        channel = result.get("primary_channel")
        return channel if type(channel) is int and 1 <= channel <= 16 else None
