# W22 — Editable style designer and curated ensemble

Status: automated and deployed-software evidence complete; subjective listening
and physical accordion tests pending.

## Scope

Replace the unwanted sampled string backing with a curated ensemble of piano,
acoustic guitar, drums, and flute. Add a small, safe style designer that can
create, update, and delete named accompaniment configurations without claiming
to be the future style-v1 phrase editor.

## Implementation

- All six built-in arrangements now select General MIDI Acoustic Grand Piano
  (program 0), Steel Acoustic Guitar (program 25), Flute (program 73), and the
  General MIDI drum kit. No built-in palette selects a string, accordion, or
  brass preset.
- A custom style references one built-in rhythmic template and stores its name,
  starting tempo, four role instruments and levels, plus drum enable and level.
  Each role can also be turned off.
- The backend validates the complete document, assigns opaque custom IDs, and
  replaces `custom-styles.json` atomically in `OSTINATO_STATE_DIRECTORY`.
- The arranger catalog merges built-in and custom entries. A saved style can be
  selected for playback, reopened for editing, or removed while transport is
  stopped. Built-in templates are never modified.
- The browser requires a second click to confirm deletion. Creating or updating
  a style selects it in the live arranger after the backend accepts it.

## Verification

- **automated:** store tests cover create, update, reload, delete, invalid
  instruments, invalid templates, and the missing-file case.
- **automated:** API tests cover the instrument catalog and full style CRUD.
- **automated:** arranger tests cover catalog selection and applying a saved
  template; renderer tests lock every built-in palette and verify custom
  programs, levels, and muted layers.
- **automated:** isolated TimGM6mb analysis measured Acoustic Guitar program 25
  from MIDI 36–96 within approximately 10 cents and Flute program 73 from MIDI
  60–105 within approximately 8 cents. This analysis did not exercise the
  FR-4X or the user's audio route.
- **automated:** the complete local suite passed with 136 tests; Ruff formatting
  and mypy checks also passed.
- **deployed software:** Compose rebuilt and restarted the service successfully;
  the container is healthy and `/api/health` returns `ok`. Inspection inside the
  running image confirmed every built-in palette uses programs 25, 0 or 73 for
  its pitched roles, plus the General MIDI drum kit.
- **deployed software:** browser inspection at 780 CSS pixels showed a scrollable
  two-column modal with all templates, four role cards, drums and responsive
  controls. A browser-driven create, rename/update, select and guarded delete
  cycle completed successfully; the temporary verification style was removed.
- **pending:** performer listening acceptance of every built-in and saved style,
  balance, and transition behavior on the selected host output.

## Superseded designer boundary

W23 expands the optional custom palette to basses, strings, guitars, keys and
winds and adds meter, phrase length, register and articulation controls. The
six built-in palettes remain string-free. See
`w23-advanced-style-designer.md` for the current designer contract.

## Safety boundary

Ostinato still generates accompaniment audio only. The FR-4X analog audio stays
on its direct mixer path. No MIDI channel, ALSA port, Bluetooth sink, or
SoundFont path is inferred by this milestone, and no proprietary arranger data
is imported.
