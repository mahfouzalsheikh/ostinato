# W29 — Higher-quality sampled accompaniment

Status: software and deployed-software gates complete; listening gate rejected
by the owner and superseded by W30.

## Scope

This milestone replaces TimGM6mb as the container's default accompaniment
library with MuseScore General HQ, adds a reproducible matched A/B render, and
collects objective level evidence before any subjective palette or articulation
changes. It does not add an SFZ engine or claim that physical playback sounds
more realistic.

## Assets and licensing

- The Docker image installs Debian's `musescore-general-soundfont` package and
  uses its exact `/usr/share/sounds/sf3/MuseScore_General_Full.sf3` path.
- Debian describes that package as a high-quality, GM-compatible, MIT-licensed
  library with separate ensemble samples. Package copyright and sample-source
  metadata remain installed in the image.
- TimGM6mb remains installed under GPL-2 at the package-owned
  `/usr/share/sounds/sf2/TimGM6mb.sf2` path solely as the explicit legacy A/B
  reference.
- No proprietary or externally downloaded audio assets were added.

Source: <https://packages.debian.org/bookworm/sound/musescore-general-soundfont>

## Implementation evidence

- Compose selects and names MuseScore General HQ explicitly; arranger status
  reports that configured library name.
- `ostinato soundfont-compare` renders the same four-bar C-Am-F-G7 progression
  through both libraries for every built-in style or one selected style.
- The command writes matched 48 kHz stereo WAV files and a JSON manifest with
  peak and RMS dBFS, clipped-sample counts, and frame counts.
- Input paths and style names are validated. Rendering is offline and does not
  open a MIDI or audio device.
- Existing per-style gains are unchanged: the matched render showed no clipping
  and closely aligned median levels, so subjective listening should precede any
  mix recalibration.

## Automated comparison result

The W29 image rendered 28 WAV files across all fourteen styles:

- MuseScore General HQ: maximum peak `-0.85 dBFS`, median RMS `-23.74 dBFS`,
  clipped samples `0`.
- TimGM6mb: maximum peak `-2.87 dBFS`, median RMS `-23.72 dBFS`, clipped
  samples `0`.
- Per-style RMS differences were between `-1.53 dB` and `+1.30 dB`.

These are automated software measurements, not perceptual quality scores.

## Verification boundary

- Targeted CLI, comparison, arranger, and SoundFont tests: `55 passed`.
- Strict mypy checks for the new comparison and CLI paths: passed.
- Docker image build: passed; both package-owned SoundFont files were present.
- All-style matched render: passed; 28 files produced with no clipped samples.
- Complete local check suite: passed; `144 passed`, browser checks passed,
  formatting and lint passed, and strict mypy passed.
- Recreated service: healthy. `/api/health` returned `{"status":"ok"}` and the
  status API reported `FluidSynth · MuseScore General HQ`, stopped transport,
  no active preview, and no error.
- Deployed default-path comparison: passed; the in-container command produced
  the expected two WAV files and manifest for `classic_waltz`.
- Owner A/B listening and output-volume calibration: pending.
- Physical FR-4X, mixer, amplifier, and speaker playback: untested.

## Human gate result

The owner reported that the result still sounded like an old video game and did
not perceive a meaningful realism improvement. W30 therefore replaces Classic
Waltz's shared GM palette with dedicated open SFZ instruments. W29 remains the
renderer for the other styles and custom-style system; no perceptual-quality
claim is attached to it.
