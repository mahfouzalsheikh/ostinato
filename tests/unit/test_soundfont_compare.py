from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from ostinato.computer_audio import DemoAudioConfig
from ostinato.domain import ChordState
from ostinato.sfz_audio import SfzStylePaths, SfzWaltzPaths
from ostinato.soundfont_compare import (
    SoundFontVariant,
    measure_pcm,
    render_open_sample_comparison,
    render_soundfont_comparison,
    render_waltz_realism_comparison,
)


class FakeComparisonRenderer:
    def __init__(self) -> None:
        self.closed = False

    def render(self, frame_count: int, _chord: ChordState | None) -> bytes:
        return struct.pack("<hh", 1_000, -1_000) * frame_count

    def close(self) -> None:
        self.closed = True


class SoundFontComparisonTests(unittest.TestCase):
    def test_pcm_measurements_report_level_frames_and_clipping(self) -> None:
        pcm = struct.pack("<hhhh", 32_767, -32_768, 1_000, -1_000)

        peak, rms, clipped, frames = measure_pcm(pcm)

        self.assertEqual(peak, 0.0)
        self.assertIsNotNone(rms)
        self.assertEqual(clipped, 2)
        self.assertEqual(frames, 2)

    def test_comparison_writes_matched_wavs_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            hq = temporary / "hq.sf3"
            legacy = temporary / "legacy.sf2"
            hq.write_bytes(b"test")
            legacy.write_bytes(b"test")
            renderers: list[FakeComparisonRenderer] = []

            def factory(
                _style: str, _config: DemoAudioConfig, _path: str
            ) -> FakeComparisonRenderer:
                renderer = FakeComparisonRenderer()
                renderers.append(renderer)
                return renderer

            results = render_soundfont_comparison(
                temporary / "comparison",
                ("classic_waltz",),
                (
                    SoundFontVariant("hq", "HQ", hq),
                    SoundFontVariant("legacy", "Legacy", legacy),
                ),
                renderer_factory=factory,
            )

            manifest = json.loads(
                (temporary / "comparison" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(results), 2)
            self.assertEqual(len(manifest["results"]), 2)
            self.assertEqual(manifest["progression"], ["C", "Am", "F", "G7"])
            self.assertTrue(
                (temporary / "comparison" / "classic_waltz--hq.wav").is_file()
            )
            self.assertTrue(all(renderer.closed for renderer in renderers))

    def test_comparison_requires_real_explicit_soundfont_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            variants = (
                SoundFontVariant("hq", "HQ", temporary / "missing.sf3"),
                SoundFontVariant("legacy", "Legacy", temporary / "missing.sf2"),
            )

            with self.assertRaisesRegex(FileNotFoundError, "SoundFont does not exist"):
                render_soundfont_comparison(
                    temporary / "comparison", ("modern_tango",), variants
                )

    def test_waltz_comparison_renders_gm_and_open_sample_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            paths = {}
            for field in (
                "library",
                "piano",
                "bass",
                "flute",
                "cello",
                "violin",
                "drums",
            ):
                path = temporary / field
                path.write_bytes(b"test")
                paths[field] = path
            soundfont = temporary / "hq.sf3"
            soundfont.write_bytes(b"test")

            results = render_waltz_realism_comparison(
                temporary / "comparison",
                soundfont,
                SfzWaltzPaths(**paths),
                renderer_factory=lambda _style, _config, _path: (
                    FakeComparisonRenderer()
                ),
            )

        self.assertEqual(
            [Path(result.file).stem for result in results],
            ["classic_waltz--gm-hq", "classic_waltz--sfz-open"],
        )

    def test_open_sample_comparison_renders_requested_genre_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            waltz_values = {}
            for field in (
                "library",
                "piano",
                "bass",
                "flute",
                "cello",
                "violin",
                "drums",
            ):
                path = temporary / field
                path.write_bytes(b"test")
                waltz_values[field] = path
            style_values = {}
            for field in (
                "acoustic_guitar",
                "electric_guitar",
                "electric_bass_finger",
                "electric_bass_pick",
                "drum_kit",
                "clarinet",
                "trumpet",
            ):
                path = temporary / field
                path.write_bytes(b"test")
                style_values[field] = path
            soundfont = temporary / "hq.sf3"
            soundfont.write_bytes(b"test")

            results = render_open_sample_comparison(
                temporary / "comparison",
                ("bossa_nova", "funk_pocket"),
                soundfont,
                SfzStylePaths(waltz=SfzWaltzPaths(**waltz_values), **style_values),
                renderer_factory=lambda _style, _config, _path: (
                    FakeComparisonRenderer()
                ),
            )

        self.assertEqual(len(results), 4)
        self.assertEqual(
            [result.file for result in results],
            [
                "bossa_nova--gm-hq.wav",
                "bossa_nova--sfz-open.wav",
                "funk_pocket--gm-hq.wav",
                "funk_pocket--sfz-open.wav",
            ],
        )


if __name__ == "__main__":
    unittest.main()
