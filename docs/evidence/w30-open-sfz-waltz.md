# W30 — Open multi-sample Classic Waltz

Status: software, deployed-software, and owner listening gates complete;
superseded by the all-built-in W31 expansion.

## Scope

The owner rejected W29's shared General MIDI result as still sounding like an
old video game and explicitly accepted a larger distribution for better audio
quality. W30 gives the built-in Classic Waltz a dedicated open SFZ instrument
rack. It does not replace the General MIDI engine for the other presets or
custom styles, and it does not claim perceptual realism before owner listening.

## Assets and licensing

- sfizz 1.2.3 is built from pinned commit
  `4e70dc0bef53b41f2853ed46e26f5911114c92d0` under BSD-2-Clause.
- Salamander Grand Piano V3 (Alexander Holm) supplies a 16-velocity-layer
  piano with release and resonance samples under CC BY 3.0.
- Karoryfer Meatbass v1.001 supplies four-layer, four-round-robin pizzicato
  bass, and Swirly Drums v1.104 supplies brushed drums; both are CC0.
- Selected VSCO 2 CE flute, cello, and violin mappings/samples come from pinned
  commit `6dd651d55dde97fd4028699be9d4481f26917891` under CC0.
- Downloaded archives have fixed SHA-256 checksums. Exact URLs, hashes,
  attribution, and license links are in `docs/style-library-sources.md`; source
  license/readme files remain in the image beside the extracted samples.
- The extracted sample payload is approximately 3.3 GB. No proprietary sample
  library is included.

## Implementation evidence

- One sfizz synth is loaded for each piano, pizzicato bass, flute, cello,
  violin, and brushed-drum SFZ file. Each has independent gain, pan, and volume.
- The renderer uses velocity-sensitive samples, staggered piano chord attacks,
  a monophonic flute line, sustained cello/violin support, and Waltz-specific
  brushed percussion instead of changing only General MIDI program numbers.
- A harmony correction immediately silences stale melodic voices and schedules
  the replacement chord through the same low-latency renderer boundary.
- Native rendering is split into blocks no larger than sfizz's configured
  real-time buffer. This was discovered and corrected during the first native
  comparison, which had rejected oversized spans.
- `ostinato waltz-compare` renders the former MuseScore-GM Waltz beside the new
  SFZ rack with identical C-Am-F-G7 content, 48 kHz stereo format, and objective
  peak/RMS/clipping measurements.
- Built-in Classic Waltz reports `sfizz · open sampled orchestra`. Other
  presets and custom styles continue to report and use their configured
  FluidSynth SoundFont.

## Native comparison

The corrected, level-calibrated native render produced two 360,000-frame WAV
files:

- MuseScore General HQ GM: peak `-9.80 dBFS`, RMS `-29.07 dBFS`, clipped
  samples `0`.
- Open SFZ rack: peak `-8.61 dBFS`, RMS `-29.65 dBFS`, clipped samples `0`.

The RMS difference is `-0.58 dB`, close enough for a useful listening
comparison. These figures prove valid output, matching duration, safe headroom,
and approximate level alignment; they are not perceptual quality scores.

## Verification boundary

- Targeted SFZ rack, renderer, service-selection, CLI, and comparison tests:
  passed.
- Native sfizz loaded all six explicit mappings and rendered the complete A/B
  pair without an invalid-buffer or missing-file error.
- Complete local check suite: passed; `150 passed`, browser JavaScript checks
  passed, all 53 files were formatted, Ruff passed, and strict mypy passed.
- Final Docker image build: passed. The resulting compressed image size reported
  by Docker is 2,103,822,342 bytes.
- Final-image A/B render: passed with the same metrics above, no missing mapping,
  invalid-buffer, or clipped-sample error.
- Hardware-free final-image benchmark: six instruments loaded in 1.899 seconds,
  then rendered 7.5 seconds of 480-frame real-time chunks in 1.761 seconds
  (`4.26×` real time). This is software throughput evidence, not an acoustic
  latency measurement.
- Recreated service: healthy. `/api/health` returned `{"status":"ok"}`. After
  selecting Classic Waltz, arranger status reported
  `sfizz · open sampled orchestra`, stopped transport, no active preview, and no
  error. Service logs showed clean startup and successful verification requests.
- Physical FR-4X, mixer, amplifier, and speaker playback: untested.
- Owner realism assessment: accepted. The owner reported that Classic Waltz was
  "definitely at a completely different level of quality" and requested the
  same approach for the other styles.
- Detailed physical latency/endurance measurements: untested.

## Human gate result

The owner accepted the realism improvement and explicitly authorized extending
the same open multi-sample approach. W31 preserves this accepted Waltz rack
unchanged while adding genre-specific profiles for the other thirteen built-in
styles.
