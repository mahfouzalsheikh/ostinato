"""Render matched SoundFont samples for an explicit listening comparison."""

from __future__ import annotations

import json
import math
import sys
import wave
from array import array
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from ostinato.computer_audio import DEMO_STYLES, DemoAudioConfig
from ostinato.domain import ChordQuality, ChordState
from ostinato.sfz_audio import (
    SfzStyleArrangementRenderer,
    SfzStylePaths,
    SfzWaltzArrangementRenderer,
    SfzWaltzPaths,
)
from ostinato.soundfont_audio import SoundFontArrangementRenderer

COMPARISON_SCHEMA_VERSION = 1
COMPARISON_SAMPLE_RATE = 48_000
COMPARISON_PROGRESSION = (
    ChordState(0, ChordQuality.MAJOR, None, 1.0, ("comparison-c",), 0),
    ChordState(9, ChordQuality.MINOR, None, 1.0, ("comparison-am",), 0),
    ChordState(5, ChordQuality.MAJOR, None, 1.0, ("comparison-f",), 0),
    ChordState(
        7,
        ChordQuality.DOMINANT_SEVENTH,
        None,
        1.0,
        ("comparison-g7",),
        0,
    ),
)


class ComparisonRenderer(Protocol):
    """Small renderer boundary used by hardware-free comparison tests."""

    def render(self, frame_count: int, chord: ChordState | None) -> bytes: ...

    def close(self) -> None: ...


ComparisonRendererFactory = Callable[[str, DemoAudioConfig, str], ComparisonRenderer]


@dataclass(frozen=True, slots=True)
class SoundFontVariant:
    """One explicitly named SoundFont used in a comparison."""

    id: str
    name: str
    path: Path


@dataclass(frozen=True, slots=True)
class RenderMetrics:
    """Objective PCM measurements for one comparison file."""

    style: str
    soundfont: str
    file: str
    peak_dbfs: float | None
    rms_dbfs: float | None
    clipped_samples: int
    frames: int


def _level_dbfs(value: float) -> float | None:
    if value <= 0:
        return None
    return round(20 * math.log10(value / 32_767), 2)


def measure_pcm(pcm: bytes) -> tuple[float | None, float | None, int, int]:
    """Return peak/RMS dBFS, clipped-sample count, and stereo frame count."""

    if len(pcm) % 4:
        raise ValueError("PCM must contain complete 16-bit stereo frames")
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return None, None, 0, 0
    peak = max(abs(sample) for sample in samples)
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    clipped = sum(abs(sample) >= 32_767 for sample in samples)
    return _level_dbfs(peak), _level_dbfs(rms), clipped, len(samples) // 2


def _native_renderer(
    style_id: str, config: DemoAudioConfig, soundfont_path: str
) -> ComparisonRenderer:
    return SoundFontArrangementRenderer(style_id, config, soundfont_path)


def render_soundfont_comparison(
    output_directory: Path,
    style_ids: Sequence[str],
    variants: Sequence[SoundFontVariant],
    *,
    renderer_factory: ComparisonRendererFactory = _native_renderer,
) -> tuple[RenderMetrics, ...]:
    """Write matched four-bar WAV files and a machine-readable manifest."""

    if not style_ids:
        raise ValueError("at least one style is required")
    if len(variants) < 2:
        raise ValueError("at least two SoundFonts are required for comparison")
    unknown = [style_id for style_id in style_ids if style_id not in DEMO_STYLES]
    if unknown:
        raise ValueError(f"unknown arranger style: {unknown[0]}")
    for variant in variants:
        if not variant.path.is_file():
            raise FileNotFoundError(f"SoundFont does not exist: {variant.path}")

    output_directory.mkdir(parents=True, exist_ok=True)
    metrics: list[RenderMetrics] = []
    for style_id in style_ids:
        definition = DEMO_STYLES[style_id]
        config = DemoAudioConfig(
            tempo_bpm=definition.default_tempo_bpm,
            sample_rate=COMPARISON_SAMPLE_RATE,
            chunk_frames=480,
        )
        frames_per_bar = round(
            definition.beats_per_bar
            * 60
            * config.sample_rate
            / definition.default_tempo_bpm
        )
        for variant in variants:
            renderer = renderer_factory(style_id, config, str(variant.path))
            try:
                pcm = b"".join(
                    renderer.render(frames_per_bar, chord)
                    for chord in COMPARISON_PROGRESSION
                )
            finally:
                renderer.close()
            filename = f"{style_id}--{variant.id}.wav"
            output_path = output_directory / filename
            with wave.open(str(output_path), "wb") as stream:
                stream.setnchannels(2)
                stream.setsampwidth(2)
                stream.setframerate(config.sample_rate)
                stream.writeframes(pcm)
            peak, rms, clipped, frames = measure_pcm(pcm)
            metrics.append(
                RenderMetrics(
                    style=style_id,
                    soundfont=variant.name,
                    file=filename,
                    peak_dbfs=peak,
                    rms_dbfs=rms,
                    clipped_samples=clipped,
                    frames=frames,
                )
            )

    manifest: Mapping[str, object] = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "sample_rate": COMPARISON_SAMPLE_RATE,
        "progression": ("C", "Am", "F", "G7"),
        "results": [asdict(result) for result in metrics],
    }
    (output_directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return tuple(metrics)


def render_waltz_realism_comparison(
    output_directory: Path,
    soundfont_path: Path,
    sfz_paths: SfzWaltzPaths,
    *,
    renderer_factory: ComparisonRendererFactory | None = None,
) -> tuple[RenderMetrics, ...]:
    """Render the former GM waltz beside the dedicated open-sample rack."""

    sfz_paths.validate()

    if renderer_factory is None:

        def renderer_factory(
            style_id: str, config: DemoAudioConfig, source_path: str
        ) -> ComparisonRenderer:
            if Path(source_path) == sfz_paths.library:
                return SfzWaltzArrangementRenderer(config, sfz_paths)
            return SoundFontArrangementRenderer(style_id, config, source_path)

    return render_soundfont_comparison(
        output_directory,
        ("classic_waltz",),
        (
            SoundFontVariant("gm-hq", "MuseScore General HQ (GM)", soundfont_path),
            SoundFontVariant(
                "sfz-open", "Dedicated open sampled orchestra", sfz_paths.library
            ),
        ),
        renderer_factory=renderer_factory,
    )


def render_open_sample_comparison(
    output_directory: Path,
    style_ids: Sequence[str],
    soundfont_path: Path,
    sfz_paths: SfzStylePaths,
    *,
    renderer_factory: ComparisonRendererFactory | None = None,
) -> tuple[RenderMetrics, ...]:
    """Render every requested built-in through GM and its open-sample rack."""

    sfz_paths.validate()

    if renderer_factory is None:

        def renderer_factory(
            style_id: str, config: DemoAudioConfig, source_path: str
        ) -> ComparisonRenderer:
            if Path(source_path) != sfz_paths.waltz.library:
                return SoundFontArrangementRenderer(style_id, config, source_path)
            if style_id == "classic_waltz":
                return SfzWaltzArrangementRenderer(config, sfz_paths.waltz)
            return SfzStyleArrangementRenderer(style_id, config, sfz_paths)

    return render_soundfont_comparison(
        output_directory,
        style_ids,
        (
            SoundFontVariant("gm-hq", "MuseScore General HQ (GM)", soundfont_path),
            SoundFontVariant(
                "sfz-open", "Genre-profiled open sample rack", sfz_paths.waltz.library
            ),
        ),
        renderer_factory=renderer_factory,
    )
