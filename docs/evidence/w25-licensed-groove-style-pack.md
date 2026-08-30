# W25 — Licensed human-groove style pack

Status: automated verification complete; deployed listening acceptance pending.

## Scope

Research usable arranger-style libraries and enrich the built-in catalog without
copying material whose redistribution rights are unclear. Preserve live chord
following, the direct FR-4X analog path, and the existing custom-style workflow.

## Implementation

- The built-in catalog grows from six to fourteen styles with Motown Soul, Funk
  Pocket, Soft Pop Ballad, Country Two-Step, Reggae One Drop, Brazilian Samba,
  New Orleans Cha-Cha, and Blues Shuffle.
- The new drum feels are reduced adaptations of named Groove MIDI Dataset
  performances under CC BY 4.0. Bass, chord, backing, and flute parts are
  original harmony-relative Ostinato patterns. Full attribution and the exact
  source-performance identifiers are in `docs/style-library-sources.md`.
- `GrooveBar` now carries independent kick, snare, and auxiliary-percussion
  accents. Both procedural and SoundFont renderers apply them, preserving
  dynamic hierarchy and ghost-note contrast rather than emitting every hit at
  one velocity.
- Every new style has four differentiated measures, phrase-end fills, calibrated
  intro/main/ending level arcs, a default tempo, and string-free piano,
  acoustic-guitar, flute, and General MIDI drum palettes.
- Catalog APIs expose provenance so clients and future import/export tools can
  distinguish original patterns from attributed adaptations.

## Research boundary

MMA's large library is GPL-2.0 and JJazzLab's downloadable community/Yamaha
style collection lacks clear per-file redistribution provenance. Neither was
bundled. Yamaha documentation informed only the part/section vocabulary. No
proprietary style data, file semantics, or accordion MIDI assumptions were
introduced.

## Verification

- **automated:** the complete local suite passed with 147 tests; formatting,
  lint, and mypy static typing also passed. Catalog tests require all fourteen identifiers and exactly eight
  CC BY adaptations; all styles render distinct PCM, contain valid four-bar
  phrases, and preserve recognized chord pitch classes for all supported chord
  qualities.
- **automated:** SoundFont tests verify every style has a palette and confirm
  multiple kick and snare velocities in the human-groove pack.
- **deployed software:** Compose rebuilt and restarted healthy. The live API
  exposed fourteen styles and their provenance. A browser audition of the
  unsaved Funk Pocket template started successfully through the configured
  FluidSynth output, reported active preview state, stopped cleanly, and logged
  no browser errors.
- **subjective:** balance, realism, phrase flow, intro/ending quality, and live
  playability through the performer's selected output remain pending listening
  acceptance.

## Safety boundary

The pack generates accompaniment audio only. It does not transmit MIDI to the
FR-4X, alter its analog mixer path, choose an audio sink, or claim hardware was
exercised.
