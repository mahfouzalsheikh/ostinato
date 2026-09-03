# W38 — KORG Pa80 reference import and offline audio

Status: converter-reference, real-SMF import, offline-render, and deployed-
software gates complete; source-chord semantics, live arranger integration,
hardware, and performer listening gates pending.

## Scope

Use the user-supplied official `Styl-v01.zip` without requiring Windows or KORG
hardware, obtain a verifiable Standard MIDI interchange representation, import
all eight styles into Ostinato's vendor-neutral model, and render bounded audio
references. Stop before inventing chord rules that the exported files do not
contain.

KORG's official [Pa80 Style to MIDI 1.06 page](https://www.korg.com/us/support/download/software/1/192/2455/)
describes the freeware utility as converting individual Chord Variations to and
from SMF for Pa80/Pa60/Pa50-family instruments and explicitly says it is not an
automatic song-to-style converter. KORG's official
[arranger tutorial](https://www.korg.com/tw/features/arrangers/tutorials/)
specifies format-0 SMF, lowercase `EnCVn` filenames, and the style-channel map:
Bass 9, Drum 10, Percussion 11, and ACC1–ACC5 on 12–16. The official
[Arranger Bonusware catalog](https://www.korg.com/us/features/arrangers/bonusware/)
identifies volume 1 as eight styles spanning Ballad, Jazz, Latin, and Funk.

## Inputs and conversion boundary

- Local archive: `assets/styles/korg/downloads/Styl-v01.zip`
- Archive size: 83,989 bytes
- Archive SHA-256:
  `03fec1a6e09424a6854e072d9f09dffe34e86f750cd4a1da9ba409aaef2ac822`
- Native bank: `Styl-v01.set/STYLE/USER01.STY`
- Native bank size: 92,348 bytes
- Native bank SHA-256:
  `4c2a0ba362625c7a2cc18c207cf5d4e1046ab06288c4b9af44c1559cf6a8367f`
- Converter archive SHA-256:
  `d5dae205afc9cdea4220b24964a11e4e14bbd3be77ac17ebce9df7e5708f08d2`
- `PaStyleToMidi.exe` size: 745,984 bytes
- Converter executable SHA-256:
  `0d0997432c6b722f62e6f7cf143bf185df912456e317cef772a7313db9dd9ef7`

The legacy GUI converter was run under 32-bit Wine in a disposable local
container. This did not install system packages, require a Windows host, or
exercise KORG hardware. The converter and all KORG inputs/derivatives remain
outside version control. The workflow used an official executable obtained
from KORG, but an arbitrary future SMF directory cannot authenticate its own
origin; generated JSON therefore says `not_authenticated_by_file_format` and
records the official format profile separately.

## Implemented behavior

- A strict directory importer recognizes KORG's documented lowercase filename
  ranges: Variation 1–4 CV1–CV6, and Intro/Fill/Ending 1–2 CV1–CV2.
- Every file must be a one-track format-0 SMF with a positive PPQ resolution,
  exactly one time signature at tick zero, consistent resolution and meter,
  supported MIDI event types, and only documented style channels.
- One-based source channels 9–16 map to Bass, Drum, Percussion, and ACC1–ACC5;
  the internal zero-based channels 8–15 are retained explicitly.
- Notes, controller changes, bank select, program changes, and pitch-wheel
  events are retained in integer ticks. Multiple Chord Variations remain
  separate and source provenance is stored in readable version-1 JSON.
- The existing marker-based SMF importer also retains pitch-wheel events.
- A hardware-free renderer plays any imported element/CV into 48 kHz stereo
  PCM using absolute integer tick-to-frame conversion. It leaves source pitches
  unchanged, preserves KORG bank/program values in JSON, and labels its bank-0
  General MIDI playback as an approximation.
- FluidSynth's native pitch-bend operation is available through the existing
  synth wrapper and is covered by the offline event-dispatch test.

## Observed real-style results

All 128 converter-produced Chord Variation files are 384 PPQ, format 0, and
one track. The converter declares 120 BPM in every export; this is a conversion
value and is **not** authenticated as each source style's original tempo. All
eight styles use the complete documented channel set.

| Style | CV files | Meter | Imported events | Notes | Pitch bends |
| --- | ---: | ---: | ---: | ---: | ---: |
| SweetBallad | 14 | 4/4 | 2,430 | 1,803 | 176 |
| Blue Ballad | 12 | 4/4 | 2,238 | 1,572 | 149 |
| Unpl.Ballad | 14 | 4/4 | 3,566 | 3,061 | 59 |
| Be4 Swing | 17 | 2/4 | 3,028 | 2,592 | 0 |
| Latin Disco | 16 | 4/4 | 3,819 | 3,435 | 0 |
| Ba' Bayon | 18 | 4/4 | 4,987 | 4,404 | 91 |
| FashionFunk | 21 | 4/4 | 5,569 | 5,085 | 0 |
| Black Funk | 16 | 4/4 | 5,292 | 4,513 | 355 |
| **Total** | **128** |  | **30,929** | **26,465** | **830** |

One Variation 1/CV1 WAV was rendered for each style with the exact local
`/usr/share/sounds/sf2/FluidR3_GM.sf2` reference. Be4 Swing is 2.5 seconds and
the other references are 4.5 seconds, including a 0.5-second release tail.
Measured peak levels range from -13.5 to -5.1 dBFS, so none reaches digital
clipping. A separate SweetBallad Intro 1/CV1 render exercised 23 real
pitch-wheel events and produced a valid 6.5-second WAV with a -5.8 dBFS peak.
These measurements are signal evidence, not subjective listening approval.

## Automated evidence

- Focused KORG importer, imported-audio, and SoundFont tests: `34 passed`.
- Complete required local suite: `193 passed`.
- Ruff lint and formatting and strict mypy: passed.
- `git diff --check`: passed.
- No browser JavaScript test files are present in the current tree; the required
  `scripts/run-checks.sh` therefore has no JavaScript test step.
- No downloaded KORG source, exported SMF, converted JSON, or rendered WAV is
  tracked by Git.

## Deployed-software evidence

- Added explicit `.dockerignore` boundaries for all user-supplied KORG sources
  and generated derivatives, plus an automated regression test for those
  paths. The corrected Docker build context was 14.97 kB.
- Rebuilt and recreated the Compose service from image manifest
  `sha256:8a946a79fa2932c80336fd5bc7847483df6646ec6705c57855cb8acf9228e70a`.
- Corrected container start: `2026-09-02T20:59:15.063172865Z`.
- Compose health: **healthy**; `/` and `/api/health` both returned HTTP 200,
  with `{"status":"ok"}` from the health API.
- In-container imports confirmed the Pa80 importer, offline renderer, and native
  FluidSynth pitch-bend operation are available.
- An in-container filesystem check confirmed the KORG download, extraction,
  MIDI, converted JSON, and WAV paths contain no files.
- Recent service logs showed successful startup and health requests with no
  `ERROR` or traceback entries.
- No arranger preview or transport was started during deployment verification.

## Evidence boundary and next gate

- Official converter behavior and documentation: **observed**.
- Real `Styl-v01` converter export and structural validation: **observed by
  software**.
- Vendor-neutral import of all eight styles: **observed by software**.
- Offline PCM generation and non-clipping measurements: **observed by
  software**.
- Original KORG timbres and drum kits: **unavailable**; General MIDI rendering
  is an explicit approximation.
- Source chord, NTT/NTR, Chord Table, and Chord Variation selection semantics:
  **not present in these exports and pending**.
- Chord-responsive transformation, section scheduling, continuous looping, and
  live arranger/UI integration: **pending**.
- Native direct `.STY` musical decoding: **unsupported and deferred**.
- KORG and FR-4X hardware behavior: **untested**.
- Musical fidelity and performer playability: **pending listening gate**.

The next milestone may connect these imported patterns to live accompaniment
only after choosing and validating a conservative source-chord/transposition
policy. The real exports alone do not justify inventing that policy.
