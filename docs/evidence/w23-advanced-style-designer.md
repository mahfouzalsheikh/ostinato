# W23 — Advanced meter and instrumentation designer

Status: automated and deployed-software verification complete; acoustic and
physical-accordion acceptance pending.

## Scope

Advance the saved-style editor beyond a palette-and-volume overlay. Add
meter-aware template selection, configurable main-phrase measure count,
register and articulation controls, and a broad optional instrument catalog.
Do not rewrite a pattern into an incompatible meter or claim a proprietary
arranger-style editor.

## Implementation

- The schema-v2 style document records a 2/4, 3/4, or 4/4 measure validated
  against its selected groove template, plus a one-to-four-measure main loop.
  Choosing a shorter phrase loops the corresponding leading measures of the
  original four-measure template. Intros and endings keep their authored
  four-measure arc.
- Each pitched role stores instrument, level, octave shift from −2 through +2,
  and note gate from 20% through 150%. Register shifts preserve pitch class;
  the renderer clamps final MIDI notes to the valid 0–127 range.
- The catalog exposes exact General MIDI programs for keys, guitars, acoustic
  and electric basses, solo and ensemble strings, harp, and winds. Defaults
  remain piano, acoustic guitar and flute with drums. Strings are opt-in.
- General MIDI defines no dedicated mandolin patch. The clearly labeled
  **Mandolin-style pluck** uses program 25 (steel acoustic guitar), a built-in
  one-octave lift and 55% duration scale; the user's octave and gate controls
  are applied on top of that behavior.
- Schema-v1 documents remain readable. Missing meter, phrase, octave and gate
  values receive the original template meter, four measures, neutral register,
  and full note length, then serialize as schema v2 on the next write.

## Verification

- **automated:** the complete local suite passed with 140 tests. Ruff formatting
  and mypy static typing also passed. Tests cover schema-v1 migration, meter and
  register rejection, advanced persistence, phrase looping, custom program
  selection, register shift, and the expanded API catalog.
- **deployed software:** Compose rebuilt and restarted successfully; the
  container is healthy and `/api/health` returns `ok`. The running API exposes
  31 choices across Control, Keys, Guitars, Bass, Strings, and Winds.
- **deployed software:** browser inspection at 1440 × 1000 CSS pixels showed
  the complete scrollable modal. Selecting 3/4 reduced the groove list to
  Classic Waltz. A browser-driven schema-v2 save persisted a two-measure 3/4
  phrase with fingered bass guitar and a string backing shifted up one octave
  at 130% gate. It became the selected arranger style and was then deleted;
  no temporary style remains.
- **subjective:** instrument timbre, register choices, balances, and articulation
  through the selected host audio route remain pending performer review.

## Safety boundary

This milestone changes accompaniment audio only. It does not alter the saved
FR-4X mapping, send arranger MIDI to the accordion, choose an audio device, or
touch the accordion's direct analog mixer path. The catalog maps named General
MIDI programs but does not claim that every optional preset has passed a
subjective tuning and timbre review on the deployed SoundFont.
