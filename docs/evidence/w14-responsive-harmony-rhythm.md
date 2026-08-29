# W14 — Responsive harmony and left-hand rhythm tracking

## Milestone boundary

Improve how the procedural arranger follows live chord and bass movement. This
milestone changes normalized arranger state and timing inference only. It does
not change saved MIDI channel assignments, device discovery, the selected PCM
route, or any FR-4X transmission assumption.

## Implemented behavior

- Chord coalescing is measured from the first note in a cluster and reduced
  from 12 ms to 6 ms; the backend checks due work every 5 ms instead of 20 ms.
- Each chord attack is classified from its own note-on cluster. Notes still
  held from a prior chord cannot contaminate the new classification.
- Bass pitch changes update the current `ChordState` and audio engine
  immediately, including slash-bass status such as `C/G`.
- Automatic tempo consumes a deduplicated left-hand pulse stream containing
  bass attacks and one attack per chord cluster.
- Possible timing intervals are derived from both bass and chord onsets in the
  selected style's four-bar phrase. Bass-only, chord-only, and alternating
  motion are supported while very close duplicate events are ignored.

## Evidence

- **automated:** recognition becomes due 6 ms after the first cluster note,
  even when later notes arrive inside that window.
- **automated:** a new G-major cluster is recognized while C-major notes remain
  active from the previous attack.
- **automated:** a bass G attack changes an existing C harmony to `C/G`
  immediately without waiting for another chord event.
- **automated:** alternating bass/chord attacks and chord-only attacks both
  produce a stable 120 BPM estimate in deterministic tests.
- **automated:** style-derived rhythm spans cover straight, syncopated, swung,
  and two-beat patterns without MIDI or audio hardware.
- **pending:** performer confirmation of chord response, inversion behavior,
  tempo stability, and desired coalescing on representative FR-4X playing.

## Safety boundary

Automated tests use synthetic normalized events and do not claim that physical
FR-4X chord encoding or acoustic latency was exercised. The accordion's analog
voice remains on its direct mixer path; Ostinato generates accompaniment only.
