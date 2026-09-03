# W43 — Chord detection reliability and hot-path performance

Status: software gate complete; deployed-software, hardware, and listening
gates pending.

## Scope

Improve intermittent chord recognition without inventing new FR-4X messages or
changing the supported harmony vocabulary. Keep chord-button confirmation
authoritative over provisional bass-and-melody prediction.

## Design

- The former backend window expired 6 ms after the first chord note. A cluster
  whose later note arrived after that deadline could be split into unrecognized
  fragments.
- The backend now waits for 12 ms of quiet after the latest note, matching the
  browser's established coalescing interval. A 24 ms deadline from the first
  note bounds worst-case recognition latency even if events keep arriving.
- The arranger drains its bounded MIDI queue before evaluating wall-clock
  deadlines. A short scheduler delay therefore cannot split messages that are
  already buffered together.
- Exact chord-note classification is compiled once into 12-bit pitch-class
  masks. Inversions, octave doubling, the established dominant-seventh voicing
  without a fifth, and documented D-Mode codes retain their existing semantics.
- The causal harmony scorer uses precomputed chord-tone masks and one compact
  recent-note histogram instead of rebuilding candidate tone sets in every
  scoring pass. Its candidate set and weights are unchanged.
- The browser classifier uses the same mask lookup while preserving its
  established preferred-root tie-break for ambiguous displays.

## Verification

- **automated:** deterministic tests cover a staggered triad that remains
  pending until the final quiet interval, a four-note cluster resolved at the
  hard 24 ms deadline, inversion and octave-doubling classification, the
  supported root/fifth/seventh voicing, and rejection of an extra foreign pitch.
- **automated:** `pipenv run scripts/run-checks.sh` passed with 212 Python tests,
  Ruff formatting/linting, and strict mypy; all 15 browser JavaScript tests also
  passed via `node --test tests/web/*.test.mjs`.
- **automated diagnostic:** on the development host, exact four-note chord
  classification improved from about 1.97 microseconds to 0.47 microseconds per
  call (about 4.2x). A full-window harmony prediction improved from about 12.3
  microseconds to 11.3 microseconds per call. These are best-of-five software
  microbenchmarks, not end-to-end MIDI or audio latency measurements.
- **untested:** no physical FR-4X MIDI, USB timing, or accompaniment audio was
  exercised.
- **pending:** deployed-software verification and performer review with the
  passages that previously misdetected chords.

## Gate

Stop at the hardware/listening gate. Do not commit or claim musical acceptance
without owner direction.
