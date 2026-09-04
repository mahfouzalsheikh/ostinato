# W45 — Expanded style controls and musical library organization

Status: implementation, source export, and software verification complete;
performer listening gate pending.

## Scope

Expose all available main variations and additional intros/endings from the
compatible legacy source banks, add per-role mix controls, remove vendor
suffixes from style names, and organize the library by musical category.
Preserve every exportable source Chord Variation without inventing automatic
chord-table or proprietary transposition semantics. Keep accordion analog audio
on its direct mixer path; generate accompaniment only.

## Source and import boundary

- The official Pa80 Style to MIDI 1.06 executable is the same recorded reference
  used in W38. Its SHA-256 is
  `0d0997432c6b722f62e6f7cf143bf185df912456e317cef772a7313db9dd9ef7`.
- Disposable Wine/Xvfb containers run without MIDI or audio devices. A Win32
  helper reads the utility's actual bank-slot names, loaded style name, section
  tree, and default export filenames. Each must agree before saving a pattern.
  No compressed musical body is decoded by Ostinato.
- Every converter-visible Chord Variation is exported. The strict importer
  retains all valid patterns, source events, timing, banks, and programs.
  An export or structural failure is recorded; it does not establish playable
  compatibility merely because the directory header was readable.
- Full-pattern duplicate fingerprints include every section and Chord
  Variation, not just the original five CV1 sections. Previously quarantined
  aliases are reconsidered. Existing source IDs are retained where available.
- Preparation writes a new library and explicit audit report without replacing
  the active library. Source archives, raw exports, staged JSON, and backups
  remain in ignored host-local storage and outside the application image.

## Final source inventory

- **observed by software:** 126 catalog slots attempted; 125 exported and one
  (`v03-user01-003`, Jazz-4-tett) could not open in the official converter.
- **automated:** 113 accepted styles contain 1,130 CV1 sections and 1,810 total
  chord patterns. Every accepted style has four mains, two intros, two fills,
  and two endings. All 105 previous active IDs remain. Seven previous aliases
  are restored (Bonawara, Chegga, Katakofti, Masmodi1, Masmodi2, Schubi, Wachda),
  and the Arabic-bank 3/4 style is added. No full-pattern duplicates remain.
- Twelve exports are held outside the live library: Daleona, Morocco1,
  Samai 10/8, 2/4, 5/8, 9/8, 6/8, TSM 9/8, 7/8, Slow 6/8, Armen6/8Pop, and
  6/8 Ballad. Their meters either exceed the current renderer's supported
  meters or conflict with the explicit meter in the source name. No meter
  reinterpretation is inferred.
- The verified re-export changes some of the original five sections in ten
  existing styles: Beat-ChaCha, Love Theme, Shearing-Jz, Trancy, With Plugs,
  Arap, Cifteteli1, Misket, Sebari, and Vahde. The named bank slot and each
  exported node were verified; the reason for the older payload differences
  is not established. These styles particularly need performer listening.
- Host-local artifacts: `assets/styles/korg/midi/w45-full/` retains verified
  MIDI and manifests, `candidates/w45-expanded/report.json` records acceptance
  and rejection, `candidates/w45-expanded/inventory.json` records source
  differences, and `candidates/w45-before/` backs up the previous library.
  Paths without that prefix are also under `assets/styles/korg/`.

## Playback and interface

- Main Variations 1–4, Intros 1–2, and Endings 1–2 are exposed only where an
  actual CV1 pattern exists. Both fills retain their complete source lengths.
- A main-variation change queues for the next bar. An overlapping fill finishes
  before the new variation starts at its first source tick. A later choice
  replaces the pending choice; choosing the active variation cancels it.
- Intro/ending selections apply at their next trigger. The timeline follows
  the actual sounding section, its phrase length, and its integer tick origin.
- Mute, multi-track solo, and relative volume are available for every present
  source role. Mute silences active voices and suppresses future note-ons;
  volume scales source CC7 automation rather than replacing it. Mute overrides
  solo. Reset mix restores unmuted, unsoloed, 100% source balance.
- Choices and mix are owned by the backend and survive browser reloads. Style
  selection resets them; source documents are never edited by performance
  controls. Designer preview restores the selected style's controls afterward.
- The learned-control catalog adds numbered variations, intros, and endings.
  Existing generic Intro and Ending bindings use the selected number. No
  physical MIDI assignments are assumed; unsupported actions fail safely.
- Names omit the vendor suffix. Musical categories combine built-in/imported
  material across source packages. Categories are editorial interpretations
  of source names and regional package descriptions, not observed audio genre
  classification. Source attribution remains in Style details.
- Live playback continues to use CV1 and the explicit local chord-adaptation
  policy. Higher chord patterns are preserved, but their automatic chord
  assignments remain unverified. Original KORG samples, effects, NTT/key
  parameters, original tempos, and newer incompatible style formats are not
  recreated or claimed.

## Verification

- **automated:** deterministic tests cover all four main choices, quantized
  switching and phrase restart, full intro/ending lengths, fill/switch overlap,
  unchanged percussion pitches, source-volume scaling, mute/solo, queued
  note-off retiming after tempo changes, rejected choices, API state, timeline
  selection, expanded learned actions, and whole-style duplicate detection.
- **automated:** the local suite passed 239 Python tests, Ruff lint/formatting,
  and strict mypy. All 18 browser JavaScript tests passed separately.
- **observed by software:** a browser session with synthetic MIDI/audio
  boundaries selected Variation 4, Intro 2, Ending 2, and bass mute; all choices
  survived reload. Mobile layout was inspected at 390 CSS pixels and corrected
  to keep instrument labels and sliders inside the panel.
- **automated:** all 1,130 accepted CV1 sections rendered valid stereo PCM in
  an isolated, network-disabled container using FluidSynth and the configured
  MuseScore General HQ SoundFont. Each section was sampled through its first
  note and one second of output; sections with source notes produced nonzero
  output. This checks synthesis, not full-song listening or hardware output.
  The host-local `candidates/w45-expanded/audio-verification.json` records the
  section-level results.
- **observed by software:** the rebuilt Compose service is healthy. All 113
  deployed imported styles expose the expected ten sections, and all 1,130
  timeline endpoints return valid content. Browser selection of Variation 4,
  Intro 2, Ending 2, bass mute/65% volume, and drum solo survives reload.
  The mixer fits at 390 CSS pixels after removing default slider margins;
  the browser reports no console errors. Playback remains stopped.
- Build layering now keeps the large sample layers ahead of code-dependent
  environment changes, allowing subsequent code rebuilds to reuse samples.
- **untested:** physical FR-4X switches, USB timing, and host accompaniment
  output were not exercised by these software checks.
- **pending:** performer listening for levels, source-style fidelity, section
  transitions, variation timing, and practical switch assignments.

## Gate

Stop at the listening gate after deployed-software verification. Do not claim
performer acceptance or physical hardware observations from automated tests.
