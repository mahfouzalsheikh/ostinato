# W44 — Learned MIDI performance controls

Status: software and deployed-software gates complete; hardware gate pending.

## Scope

Let the performer control Intro, Fill In 1, Fill In 2, Ending, Start, and Stop
from accordion function switches without using browser buttons. Learn observed
MIDI rather than inventing FR-4X channels, controller assignments, or
proprietary encodings. Keep FR-4X analog audio on its direct mixer path.

## Source boundary

- The official [FR-4X Reference Manual](https://static.roland.com/assets/media/pdf/FR-4x_reference_e01_W.pdf)
  documents six bass-side function switches, assignable Start/Stop, Intro,
  Fill, and Ending actions, and the loss of the bass-button column nearest the
  logo while function-switch mode is enabled.
- The official [FR-4X MIDI Implementation](https://static.roland.com/assets/media/pdf/FR-4x_MIDI_Implementation_e01_W.pdf)
  documents Start (`FA`) and Stop (`FC`) transmission. It does not establish
  every desired Intro/Fill/Ending fingerprint for the performer's setup, so the
  implementation hardcodes none of them.

## Design

- Each action stores one exact raw MIDI message or a sequence of at most eight
  complete messages observed within a bounded 400 ms window.
- Bindings live inside the existing versioned MIDI profile and apply only to
  its exact saved input-port name. Changing the input through guided setup
  clears them; resaving the same input preserves them.
- Note on/off, polyphonic pressure, channel pressure, pitch bend, MIDI timing
  clock, active sensing, and bellows expression CC11 are ineligible. The path
  is for discrete switches, not continuous or musical gestures.
- Duplicate actions, identical fingerprints, and ambiguous sequence suffixes
  are rejected at the API boundary. The runtime prefers longer sequences and
  applies a 180 ms per-action cooldown.
- Capture suspends backend dispatch under the learning WebSocket owner's token.
  Disconnect and explicit cancellation both release that suspension.
- Matching and arranger dispatch remain in the backend MIDI-consumer loop, so
  saved controls continue to operate across browser reloads. Existing arranger
  commands remain the only section-state implementation.

## Verification

- **automated:** focused Python tests cover signal eligibility, defensive
  profile parsing, exact-port matching, multi-message matching amid excluded
  note/bellows traffic, sequence expiry, action cooldown, owned learning
  suspension, profile/API persistence and validation, buffered-event routing,
  and all six existing arranger command mappings.
- **automated:** browser JavaScript tests cover the matching eligibility filter,
  stable payload ordering, saved-binding reconstruction, and exact hexadecimal
  fingerprint display.
- **automated:** `pipenv run scripts/run-checks.sh` passed with 221 Python
  tests, Ruff formatting/linting, and strict mypy. All 18 browser JavaScript
  tests also passed via `node --test tests/web/*.test.mjs`.
- **deployed software:** `docker compose up -d --build` rebuilt and recreated
  the service. Compose reported the replacement container healthy; `/api/health`
  returned `{"status":"ok"}`; the page referenced `app.js?v=23` and
  `styles.css?v=20`; and the performance-control dialog and helper asset were
  served successfully.
- **deployed software:** the saved profile and exact MIDI connections restored,
  no MIDI-service error was reported, and the arranger was left stopped with
  no error. No learned bindings existed before the hardware session.
- **untested:** no physical FR-4X function-switch MIDI was captured and no USB,
  audio, stage-layout, or browser interaction was exercised.
- **pending:** configure the performer's FR-4X function switches, learn all six
  observed fingerprints, verify each section transition at low accompaniment
  volume, and decide whether giving up the logo-side bass column is acceptable.

## Gate

Stop at the hardware gate after the software suite passes. Do not claim the
FR-4X messages, physical controls, or live playability were observed until the
performer verifies them.
