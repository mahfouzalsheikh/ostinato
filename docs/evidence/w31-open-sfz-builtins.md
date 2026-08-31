# W31 — Genre-profiled open samples for all built-ins

Status: software, native-render, and deployed-software gates complete; owner
listening gate pending.

## Scope and authorization

The owner accepted W30's Classic Waltz as "definitely at a completely different
level of quality" and requested the same approach for the other styles. W31
preserves that exact accepted Waltz rack and moves the other thirteen built-ins
from shared General MIDI presets to genre-profiled open SFZ instruments. Custom
styles remain on their editable General MIDI renderer; this milestone does not
change their saved schema or reinterpret user instrument choices.

## Added open assets

- Karoryfer Shinyguitar v1.002: separate microphone and pickup recordings of an
  archtop guitar, CC0, checksum pinned.
- Karoryfer Black and Blue Basses v1.002: fingered hollowbody and picked
  solidbody five-string basses with more than 2,000 samples, CC0, checksum
  pinned.
- Virtuosity Drums commit
  `9f04cf9a734527edfbb0a4eee1f674e45bbf71bc`: a six-microphone live kit with
  General MIDI auxiliary percussion, CC0, commit pinned.

The earlier sfizz, Salamander Piano, Meatbass, Swirly Drums, and selected VSCO2
assets remain pinned. Exact source links, versions, hashes, attribution, and
licenses are in `docs/style-library-sources.md`; all supplied license/readme
files remain beside the extracted assets. The combined extracted payload is
approximately 6.2 GB. No proprietary samples are distributed.

## Genre profiles

| Styles | Bass | Comp | Fill/pad | Drums |
| --- | --- | --- | --- | --- |
| Modern/Classic Tango | Upright | Piano | Violin/cello | Live kit |
| Classic Waltz | Accepted upright/piano rack | Staggered piano | Flute/cello/violin | Brushed kit |
| Bossa Nova | Fingered electric | Acoustic archtop | Flute/cello | Live kit + GM percussion |
| Swing Foxtrot | Upright | Piano | Flute/cello | Brushed kit |
| Alpine Polka | Upright | Piano | Violin/cello | Live kit |
| Motown Soul | Fingered electric | Piano | Flute/cello | Live kit |
| Funk Pocket | Fingered electric | Electric archtop | Flute/cello | Live kit |
| Soft Pop Ballad | Fingered electric | Acoustic archtop | Flute/cello | Live kit |
| Country Two-Step | Picked electric | Acoustic archtop | Violin/cello | Live kit |
| Reggae One Drop | Fingered electric | Electric archtop | Flute/cello | Live kit |
| Brazilian Samba/New Orleans Cha-Cha | Fingered electric | Acoustic archtop | Flute/cello | Live kit + GM percussion |
| Blues Shuffle | Picked electric | Piano | Flute/cello | Live kit |

The existing style rhythms, bass roles, dynamics, sections, and causal harmony
response remain intact. Guitar and ensemble chord voices receive deterministic
millisecond attack staggering so triads do not start as a single MIDI-like
block. Harmony corrections still cut stale melodic voices immediately.

## Native A/B and level calibration

`ostinato sfz-compare` rendered the same C-Am-F-G7 progression through the
former MuseScore GM engine and the open rack for all fourteen styles. The first
pass was rejected because several SFZ files were 5–11 dB quieter. Per-style
output trims were then calibrated without changing MIDI velocity or sample
layer selection.

The corrected 28-file render showed:

- all files had the expected duration and non-silent PCM;
- SFZ-versus-GM RMS differences were from `-0.35 dB` to `+0.01 dB` (the retained
  Waltz accounts for `-0.35 dB`; every new profile is within `0.02 dB`);
- SFZ peaks were between `-14.57 dBFS` and `-2.25 dBFS`; and
- clipped samples were `0` for every file.

These measurements establish valid mappings, matched program content, usable
headroom, and level alignment. They do not establish subjective realism.

## Throughput and current limitation

A hardware-free one-bar benchmark created each native rack and rendered
480-frame chunks. Steady rendering ranged from `3.65×` to `5.13×` real time.
Cold rack load time ranged from about 1.7 seconds for Waltz/Swing to 4.9 seconds
for the largest profiles. The UI currently pays this load cost on the first
start after selecting a style. That delay must be included in owner playability
review; it is not presented as an acoustic latency measurement.

## Verification boundary

- Additional-asset build: passed; exact release checksums and commit paths were
  validated, and all expected SFZ mappings/license files exist.
- Targeted rack, renderer, profile coverage, service selection, comparison, CLI,
  arranger, and SoundFont tests: `68 passed`.
- Native all-style A/B render and invalid-buffer/missing-file scan: passed.
- Complete local check suite: passed; `157 passed`, browser JavaScript checks
  passed, all 54 files were formatted, Ruff passed, and strict mypy passed.
- Final runtime image build: passed. Docker reports an image size of
  4,709,531,382 bytes.
- Final-image all-style render: passed; 28 WAV files, 14 SFZ styles, RMS deltas
  `-0.35` to `+0.01 dB`, maximum SFZ peak `-2.25 dBFS`, clipped samples `0`, and
  no missing-file or invalid-buffer error.
- Recreated service: healthy. The API selected all fourteen built-ins and
  reported the accepted orchestra engine for Waltz and the genre ensemble for
  every other style. The original Modern Tango selection was restored; status
  then reported stopped transport, no preview, and no error. Service logs showed
  clean startup and successful verification requests.
- Physical FR-4X, mixer, amplifier, speaker, and endurance checks: untested.
- Owner realism, balance, first-start delay, timing, and playability: pending.

## Human gate

Stop after deployment for the owner to audition every built-in. Do not claim
that the new genres sound realistic, migrate custom styles to SFZ, or optimize
the cold-load architecture until the owner assesses the genre choices, balance,
timing, and first-start behavior.
