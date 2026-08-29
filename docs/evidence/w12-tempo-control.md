# W12 — Stable auto tempo and fixed-tempo control

## Milestone boundary

Correct low/unstable bass-stroke tempo estimates and add an explicit fixed BPM
control to the live arranger. This milestone does not change MIDI channel
detection, chord recognition, style audio, or sync-stop semantics.

## Evidence

- **automated:** Modern Tango gaps of 750, 750, and 500 ms normalize to 120 BPM
  using its 1.5–1.5–1 beat spacing.
- **automated:** one-second half-note bass strokes normalize to 120 BPM rather
  than incorrectly selecting 60 BPM.
- **automated:** the estimator uses integer monotonic event timestamps and a
  median window of normalized intervals.
- **automated:** fixed mode accepts 40–240 BPM, updates the backend audio tempo,
  and ignores subsequent bass timing until Bass auto is restored.
- **automated:** HTTP validation rejects an out-of-range fixed tempo.
- **pending:** performer confirmation of automatic tempo while playing both
  supplied styles.
- **pending:** performer confirmation that the fixed rotary control feels
  usable and holds the requested speed through intro, main, and ending.

## Safety boundary

No test claims physical timing or acoustic latency. The estimator consumes only
the saved bass input channel. Fixed tempo changes accompaniment timing only;
the FR-4X analog voice remains on its direct mixer path.
