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
from dataclasses import dataclass
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
from ostinato.soundfont_audio import SoundFontArrangementRenderer
from ostinato.style_designer import CustomStyle

JsonObject = dict[str, object]
CHORD_COALESCE_NS = 6_000_000
MIN_LEFT_HAND_ATTACK_GAP_NS = 110_000_000
SYNC_STOP_BARS = 2
STYLE_PREVIEW_DURATION_NS = 30_000_000_000
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


def classify_chord_notes(
    notes: Sequence[int], preferred_root: int | None = None
) -> RecognizedChord | None:
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

    actual = {note % 12 for note in valid}
    roots = list(range(12))
    if preferred_root in roots:
        roots.remove(preferred_root)
        roots.insert(0, preferred_root)
    patterns = (
        (ChordQuality.DOMINANT_SEVENTH, (0, 4, 7, 10)),
        (ChordQuality.DOMINANT_SEVENTH, (0, 4, 10)),
        (ChordQuality.DIMINISHED, (0, 3, 6, 9)),
        (ChordQuality.DIMINISHED, (0, 3, 6)),
        (ChordQuality.MAJOR, (0, 4, 7)),
        (ChordQuality.MINOR, (0, 3, 7)),
    )
    for quality, intervals in patterns:
        for root in roots:
            expected = {(root + interval) % 12 for interval in intervals}
            if actual == expected:
                return RecognizedChord(root, quality, "notes")
    return None


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

    def select_style(
        self, style_id: str, custom_style: CustomStyle | None = None
    ) -> None: ...

    def set_tempo(self, tempo_bpm: int) -> None: ...

    def set_chord(self, chord: ChordState | None) -> None: ...

    def start_main(self) -> None: ...

    def start_intro(self) -> None: ...

    def request_ending(self) -> None: ...

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
    ) -> None:
        first_style = next(iter(DEMO_STYLES.values()))
        self._style_id = first_style.id
        self._custom_style: CustomStyle | None = None
        self._tempo_bpm = first_style.default_tempo_bpm
        self._chord: ChordState | None = None
        self._sink_factory = sink_factory or (
            lambda config, device: open_pcm_sink(config, device)
        )
        self._soundfont_path = soundfont_path or os.environ.get("OSTINATO_SOUNDFONT")
        self._device: str | None = None
        self._session: RealtimeDemoArranger | None = None

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
    def error(self) -> str | None:
        """Expose an asynchronous ALSA worker failure to arranger status."""

        return self._session.error if self._session is not None else None

    @property
    def synthesis_engine(self) -> str:
        """Describe the active renderer without exposing a machine path."""

        return "FluidSynth SoundFont" if self._soundfont_path else "procedural PCM"

    def select_style(
        self, style_id: str, custom_style: CustomStyle | None = None
    ) -> None:
        if style_id not in DEMO_STYLES:
            raise ArrangerError(f"unknown arranger style: {style_id}")
        if custom_style is not None and self._soundfont_path is None:
            raise ArrangerError(
                "custom instrument styles require a configured SoundFont"
            )
        if self._session is not None:
            with suppress(AudioPlaybackError):
                self._session.close()
            self._session = None
        self._style_id = style_id
        self._custom_style = custom_style

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
            if self._soundfont_path:
                soundfont_path = self._soundfont_path

                def renderer_factory(
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
                    renderer_factory=renderer_factory,
                )
            else:
                self._session = RealtimeDemoArranger(
                    config,
                    sink,
                    style_id=self._style_id,
                )
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
        self._custom_styles: dict[str, CustomStyle] = {}
        self._clock = clock
        self._style_id = first_style.id
        self._tempo_bpm = first_style.default_tempo_bpm
        self._tempo_source = "style default"
        self._tempo_mode = TEMPO_MODE_AUTO
        self._rhythm_tracker = BassTempoTracker()
        self._auto_tempo_sources: set[str] = set()
        self._chord_coalesce_ns = chord_coalesce_ns
        self._bass_channel: int | None = None
        self._chord_channel: int | None = None
        self._active_chord_notes: set[int] = set()
        self._pending_chord_notes: set[int] = set()
        self._chord_dirty_at_ns: int | None = None
        self._last_bass_pitch_class: int | None = None
        self._chord: ChordState | None = None
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
        self._custom_styles = {style.id: style for style in styles}
        if self._style_id in DEMO_STYLES:
            return
        selected = self._custom_styles.get(self._style_id)
        if selected is None:
            self._select_style(next(iter(DEMO_STYLES)))
            return
        self._apply_style_selection(selected.id, selected)

    def configure_profile(self, profile: Mapping[str, object] | None) -> None:
        """Use only reviewed bass/chord channels from the saved profile."""

        self._bass_channel = self._profile_channel(profile, "bass")
        self._chord_channel = self._profile_channel(profile, "chord")
        self._active_chord_notes.clear()
        self._pending_chord_notes.clear()
        self._chord_dirty_at_ns = None
        self._last_bass_pitch_class = None
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
            self._update_bass(note_value % 12, timestamp_value)
            self._observe_left_hand_pulse(timestamp_value, "bass")
            self._register_sync_activity(timestamp_value)
        if channel_value == self._chord_channel:
            if active:
                self._resolve_chord_cluster(timestamp_value)
                if self._chord_dirty_at_ns is None:
                    self._pending_chord_notes.clear()
                    self._chord_dirty_at_ns = timestamp_value
                    self._observe_left_hand_pulse(timestamp_value, "chords")
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
        if self._chord_dirty_at_ns is not None:
            deadlines.append(self._chord_dirty_at_ns + self._chord_coalesce_ns)
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
        section = self._audio.section.value if self._running else "stopped"
        position_ticks = self._audio.position_ticks if self._running else None
        beat_index = (
            (position_ticks // TRANSPORT_TICKS_PER_BEAT) % definition.beats_per_bar
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
                }
                for style in self._custom_styles.values()
            ],
            "tempo_bpm": self._tempo_bpm,
            "tempo_source": self._tempo_source,
            "tempo_mode": self._tempo_mode,
            "beats_per_bar": (
                custom_style.beats_per_bar
                if custom_style is not None
                else definition.beats_per_bar
            ),
            "ticks_per_beat": TRANSPORT_TICKS_PER_BEAT,
            "position_ticks": position_ticks,
            "beat_index": beat_index,
            "running": self._running,
            "section": section,
            "sync_enabled": self._sync_enabled,
            "sync_stop_bars": SYNC_STOP_BARS,
            "chord": self._harmony_name(),
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
        base_style_id = (
            custom_style.base_style_id if custom_style is not None else self._style_id
        )
        self._audio.select_style(base_style_id, custom_style)
        self._audio.set_tempo(self._tempo_bpm)
        self._audio.set_chord(self._chord)

    def _select_style(self, value: object | None) -> None:
        if not isinstance(value, str):
            raise ArrangerError(f"unknown arranger style: {value}")
        if self._running:
            raise ArrangerError("stop the arranger before changing style")
        custom_style = self._custom_styles.get(value)
        if value not in DEMO_STYLES and custom_style is None:
            raise ArrangerError(f"unknown arranger style: {value}")
        self._apply_style_selection(value, custom_style)

    def _apply_style_selection(
        self, value: str, custom_style: CustomStyle | None
    ) -> None:
        base_style_id = (
            custom_style.base_style_id if custom_style is not None else value
        )
        definition = DEMO_STYLES[base_style_id]
        self._style_id = value
        self._reset_auto_tempo()
        if self._tempo_mode == TEMPO_MODE_AUTO:
            self._tempo_bpm = (
                custom_style.tempo_bpm
                if custom_style is not None
                else definition.default_tempo_bpm
            )
            self._tempo_source = "style default"
        self._intro_armed = False
        self._audio.select_style(base_style_id, custom_style)
        self._audio.set_tempo(self._tempo_bpm)

    def _current_definition(self) -> DemoStyleDefinition:
        custom_style = self._custom_styles.get(self._style_id)
        style_id = (
            custom_style.base_style_id if custom_style is not None else self._style_id
        )
        return DEMO_STYLES[style_id]

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
        tempo = self._rhythm_tracker.observe(
            timestamp_ns,
            beat_spans=style_rhythm_spans(
                self._current_definition().id,
                custom_style.phrase_bars if custom_style is not None else None,
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

    def _update_bass(self, pitch_class: int, timestamp_ns: int) -> None:
        self._last_bass_pitch_class = pitch_class
        chord = self._chord
        if chord is None or chord.bass_pitch_class == pitch_class:
            return
        source_ids = (*chord.source_event_ids[-3:], f"live-bass-{timestamp_ns}")
        self._chord = ChordState(
            root_pitch_class=chord.root_pitch_class,
            quality=chord.quality,
            bass_pitch_class=pitch_class,
            confidence=chord.confidence,
            source_event_ids=source_ids,
            recognized_at_ns=timestamp_ns,
        )
        self._audio.set_chord(self._chord)

    def _resolve_chord_cluster(self, now_ns: int) -> None:
        dirty_at = self._chord_dirty_at_ns
        if dirty_at is None or now_ns - dirty_at < self._chord_coalesce_ns:
            return
        notes = sorted(self._pending_chord_notes)
        self._chord_dirty_at_ns = None
        self._pending_chord_notes.clear()
        recognized = classify_chord_notes(notes, self._last_bass_pitch_class)
        if recognized is None:
            return
        self._chord = ChordState(
            root_pitch_class=recognized.root_pitch_class,
            quality=recognized.quality,
            bass_pitch_class=self._last_bass_pitch_class,
            confidence=1.0,
            source_event_ids=(f"live-{recognized.transmission}-{dirty_at}",),
            recognized_at_ns=now_ns,
        )
        self._audio.set_chord(self._chord)

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
        style = self._current_definition()
        duration_ns = round(
            SYNC_STOP_BARS * style.beats_per_bar * 60_000_000_000 / self._tempo_bpm
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
