# W20 pitch-verified reed palette evidence

Status: automated and deployed-software evidence; subjective listening test
pending.

## Root cause

The deployed TimGM6mb SoundFont's GM Tango Accordion (program 23) and Accordion
(program 21) presets contain badly tuned upper sample zones. Direct FluidSynth
measurements in the deployed container found:

- program 23 notes 73–99 approximately 46–70 cents flat;
- program 21 notes 73–96 approximately 44–68 cents flat;
- note 72, used by the earlier spot check, was within one cent and concealed
  the zone change.

These measurements used isolated notes rendered by a separate FluidSynth
instance. They did not exercise the FR-4X or Bluetooth audio path.

## Change at W20

- Modern Tango and Classic Tango now use GM Muted Trumpet (program 59), measured
  within four cents through note 96. Extreme generated voicings are folded down
  by octaves so they never enter that preset's unverified upper zones.
- Classic Waltz now uses GM English Horn (program 69), whose complete generated
  range measured without a material pitch deviation.
- Other style instruments were retained because their measured ranges did not
  reproduce the accordion-preset defect.

W22 subsequently replaced all built-in lead and backing palettes with the
curated piano, acoustic-guitar, flute, and drum ensemble. The original W20
measurements remain the reason accordion and brass presets are not exposed by
the style designer; current palette evidence is recorded in
`w22-editable-style-designer.md`.

## Verification

- Unit tests lock the replacement palette and the maximum tango brass note.
- Full local software suite: passed (`128 passed`, formatting and type checks
  passed).
- Container rebuild/restart: passed. The running image reports the replacement
  programs and note limit, the container is healthy, and `/api/health` returns
  `ok`.
- Subjective FR-4X/Bluetooth listening test: pending user confirmation.
