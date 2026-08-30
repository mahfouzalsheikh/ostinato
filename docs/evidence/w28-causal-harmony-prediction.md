# W28 — Causal bass-and-melody harmony prediction

Status: software and deployed-software gates complete; hardware and listening
gates pending.

## Scope

Use the saved bass and treble roles to predict a provisional harmony before the
performer presses the chord button. Preserve the chord button as authoritative
confirmation so an uncertain prediction is corrected immediately.

## Design

- A bass onset ranks continuation of the last confirmed chord against major,
  minor, dominant-seventh, and diminished chords rooted on the bass pitch.
- Metrical position distinguishes a likely new-measure root from an alternating
  bass inside the current harmony.
- Active melody notes provide strong chord-tone evidence; the most recent 16
  treble note-ons provide weak tonal context.
- Circle-of-fifths root motion and conservative quality priors break otherwise
  unsupported ties. Bass is evidence, not an automatically asserted inversion.
- A later treble onset can refine the still-provisional choice. A recognized
  chord-button cluster always replaces the prediction and becomes the next
  confirmed context.
- The scorer has a fixed five-candidate bound, no file or network access, and
  no model-runtime dependency in the live MIDI path.

## Why this milestone does not add a trained model

Symbolic chord-recognition research supports combining pitch content, meter,
and longer harmonic context. It also documents errors caused by assigning a
root merely because that pitch appears in the bass. Segmental and bidirectional
models use future or whole-segment evidence, however, which is unavailable at
the instant the accordion bass arrives:

- Masada and Bunescu, [Chord Recognition in Symbolic Music: A Segmental CRF
  Model](https://transactions.ismir.net/articles/10.5334/tismir.18), 2019.
- Lim, Rhyu, and Lee, [Chord Generation from Symbolic Melody Using BLSTM
  Networks](https://archives.ismir.net/ismir2017/paper/000134.pdf), 2017.

A learned causal transition model remains a sensible later layer, but it needs
representative, time-aligned performances and confirmed chord-button labels
from the owner's repertoire. The deterministic scorer establishes the logging
and correction semantics against which such a model can be evaluated.

## Verification

- **automated:** `pipenv run scripts/run-checks.sh` passed with 140 Python
  tests, browser JavaScript checks, Ruff formatting/linting, and strict mypy.
- **automated:** deterministic tests cover the D-minor/A-bass waltz ambiguity,
  downbeat versus within-measure behavior, melody-driven A7 refinement, melody
  support for retaining D minor, and chord-button correction.
- **automated diagnostic:** 100,000 scorer calls with a full 16-note melody
  window averaged about 11.5 microseconds per call on the development host.
  This is software-path evidence, not end-to-end MIDI/audio latency.
- **deployed software:** `docker compose up -d --build` rebuilt and recreated
  the service. The new container became healthy; `/api/health` returned
  `{"status":"ok"}`; arranger status reported stopped transport, no preview,
  and no backend error. Direct checks inside the container verified the Dm/A
  downbeat prediction, melody-G refinement to A7, and within-measure retention
  of D minor.
- **untested:** no physical FR-4X MIDI or accompaniment audio was exercised.
- **pending:** performer review of prediction timing and musical choices on the
  accordion, followed by capture of mispredictions for scorer calibration.

## Gate

Stop at the hardware/listening gate. Do not commit or claim musical acceptance
without owner direction.
