# W2 — Guided MIDI setup wizard

## Milestone boundary

W2 adds a local, three-step setup wizard that selects exact MIDI ports, records
user-labeled treble/bass/chord activity, ranks observed channel candidates, and
atomically saves a reviewed versioned profile. It does not infer FR-4X factory
settings, chord encodings, or left-hand button positions.

## Evidence

- **automated:** unit tests exercise distinct-channel detection, ambiguous
  shared-channel confidence, incomplete captures, profile validation, atomic
  replacement, API round trips, and deletion.
- **automated:** Ruff, mypy, the complete pytest suite, JavaScript syntax
  checking, and Compose configuration validation pass locally.
- **untested:** no physical FR-4X or other MIDI hardware was exercised by the
  automated suite.
- **pending:** confirm with the user's configured FR-4X that note activity is
  received in all three guided phases and that saved exact port names reconnect
  after a USB disconnect/reconnect.
- **pending:** confirm the inferred treble range against the physical 37-key
  keyboard and review any low-confidence shared-channel result.

## Safety and persistence

Only positive-velocity incoming note-on events are included in guided capture.
The server validates channel and note ranges, requires every selected primary
channel to be an observed candidate, and writes the profile using a
same-directory atomic replacement. Docker stores the profile in the named
`ostinato-state` volume. FR-4X analog audio remains on its direct mixer path.
