# W24 — Unsaved style preview at independent tempos

Status: automated and deployed-software verification complete; performer
listening acceptance pending.

## Scope

Let the performer hear the style designer's current unsaved configuration at
different speeds through the configured accompaniment output. Do not save the
draft, start the live arranger transport, synthesize in the browser, or change
the FR-4X audio path.

## Implementation

- The preview request validates the complete schema-v2 draft and an independent
  40–240 BPM audition tempo. It applies the exact template, phrase measures,
  instruments, registers, note gates, levels and drums to the SoundFont renderer.
- Preview uses C major as a stable comparison harmony and the exact audio output
  already selected for accompaniment. It is rejected while live transport is
  running or when no output is configured.
- Preview, Restart and Stop controls live in the designer. Changing the preview
  speed while playing restarts at that BPM. Sound-affecting form edits restart
  the audition automatically; continuous controls use a short debounce so a
  slider drag does not repeatedly tear down the audio session. Switching saved
  styles or starting a new draft keeps an active audition running.
- Stop, modal close, save, delete and any live arranger command stop preview and
  restore the selected style, tempo and harmony. The backend also enforces a
  30-second audition deadline so a disconnected browser cannot leave it playing.

## Verification

- **automated:** the complete local suite passed with 145 tests. Ruff formatting
  and mypy static typing also passed. Tests cover independent tempo, exact draft
  delivery, C-major setup, output rejection, explicit restoration, live-command
  takeover and the backend audition deadline.
- **deployed software:** Compose rebuilt and restarted successfully; the
  container is healthy, reports the FluidSynth SoundFont engine and restored
  the configured host output. `/api/health` returns `ok`.
- **deployed software:** browser inspection at 1440 × 1000 CSS pixels showed the
  complete preview strip with tempo, Preview and disabled Stop states. Starting
  the default unsaved style returned `style_previewing: true` at 120 BPM while
  live arranger `running` remained false and selected style remained Modern
  Tango. Moving the speed control posted the same unsaved form at 150 BPM. No
  service error or exception appeared.
- **deployed software:** after the live-update enhancement, changing the chord
  instrument from acoustic piano to bright piano while preview was active sent
  a second successful preview request containing `"instrument":"bright_piano"`.
  Preview remained active and the browser console reported no errors.
- **subjective:** audibility, balance, latency and behavior over the performer's
  Bluetooth or mixer route remain pending listening confirmation.

## Safety boundary

The preview produces accompaniment audio only. It does not send MIDI to the
accordion, select or replace an audio sink, persist the draft, or alter the
accordion's direct analog mixer path.
