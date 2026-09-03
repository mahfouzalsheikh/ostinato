# W36 — KORG style import foundation

Status: foundation software gate complete; real-source, playback, hardware, and
performer gates pending.

## Scope

Establish a repository-safe, offline import boundary for user-supplied KORG
style material without decoding undocumented `.STY` semantics or coupling the
live arranger to KORG binary structures.

This is the first bounded slice of the broader KORG import brief. It stops at a
human gate before real-source validation and playback integration.

## Implemented behavior

- Downloaded ZIPs, extracted packages, exported MIDI, generated inventory, and
  converted JSON are ignored by Git; only workflow documentation is tracked.
- A download helper lists the two approved official KORG catalog pages without
  scraping mutable direct-download URLs.
- The ZIP extractor validates every member before writing, rejects traversal,
  absolute paths, backslash paths, symlinks, and encrypted members, writes files
  atomically, and requires `--force` before replacing existing files.
- The inventory tool records extensions, sizes, headers, entropy, embedded ASCII
  strings, MIDI/RIFF/ZIP offsets, possible SysEx starts, and possible style
  labels. A `.STY` suffix never causes it to claim MIDI compatibility.
- A vendor-neutral version-1 model stores elements, chord variations, tracks,
  voice metadata, and note/controller/program events in integer ticks.
- The MIDI importer recognizes conservative intro, variation, fill, break, and
  ending marker spellings; preserves multiple chord-variation numbers; retains
  unknown markers; and assigns roles only from explicit Drum, Percussion, Bass,
  and ACC1–ACC5 track names.
- Import diagnostics report MIDI format, resolution, tracks, channels, note
  ranges, programs, controllers, markers, SysEx counts, tempo changes, and meter
  changes. Converted JSON preserves source provenance and explicitly records
  unknown source-chord semantics and unauthenticated origin.
- Native `.STY` input and unmarked MIDI fail with an actionable unsupported
  format error.

KORG's official [Pa80 Style to MIDI page](https://www.korg.com/us/support/download/software/1/192/2455/)
describes its legacy tool as converting individual Chord Variations to and from
Standard MIDI Files and says it does not perform automatic song-to-style
conversion. That limited official claim is why the implementation accepts
explicit markers conservatively rather than claiming one universal KORG export
layout.

## Automated evidence

- `186 passed` across the complete Python test suite.
- Eleven focused tests cover safe extraction and overwrite behavior, traversal
  rejection, opaque-file inventory, marker normalization and unknown markers,
  explicit-only track roles, multi-section MIDI import, tempo and meter,
  program/bank/controller/note events, integer-tick serialization, unsupported
  `.STY`/unmarked MIDI, and the command-line JSON conversion path.
- Ruff lint and format checks and strict mypy passed across the repository.
- All 12 browser JavaScript tests passed.
- The required `ostinato --help`, `ostinato doctor`, and scripted keyboard smoke
  commands completed successfully.
- `git diff --check` passed.

All MIDI import fixtures are generated synthetically by the tests. They contain
no downloaded KORG musical data.

## Evidence boundary and human gate

- Local software behavior: **automated**.
- Official KORG web documentation: **observed by research**.
- Real KORG package extraction and inventory: **pending**; no package was placed
  in the local download workspace during this milestone.
- Marker compatibility with a real KORG-originated MIDI export: **pending**.
- Chord transformation, section scheduling, looping, and audio playback:
  **pending** for the next milestone after real-source inspection.
- FR-4X MIDI, KORG hardware, and accompaniment audio: **untested**.
- Musical fidelity and performer playability: **pending**.

The human gate is a locally supplied, legally obtained KORG-originated style
MIDI export (preferred) or official package with its KORG model/generation and
provenance identified. It must remain outside version control. The next
milestone should inspect that sample, adjust only evidence-supported marker and
track semantics, and then connect a converted variation to the existing offline
renderer before live arranger integration.
