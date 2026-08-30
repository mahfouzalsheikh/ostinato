# W27 — Chord-only harmony recognition

Status: behavior rejected by owner; superseded by W28.

## Scope

Stop bass-channel notes from influencing live chord recognition or the
generated accompaniment harmony. Preserve bass activity for the left-hand
tempo tracker, sync start/stop, status, and accordion visualization.

## Implementation

- Chord clusters are classified only from note-on messages received on the
  reviewed chord channel.
- Bass pitch no longer biases ambiguous chord roots, becomes a slash-chord
  inversion, or updates an already recognized harmony.
- The arranger still reports the last bass pitch separately and continues to
  accept bass attacks for tempo and sync behavior.
- Explicit `ChordState` inversions remain supported by the renderer for other
  input sources; this milestone changes only live MIDI chord detection.

## Verification

- **automated:** `pipenv run scripts/run-checks.sh` passed with 137 Python
  tests, browser JavaScript checks, Ruff formatting/linting, and strict mypy.
- **deployed software:** `docker compose up -d --build` rebuilt and recreated
  the service. The new container became healthy, `/api/health` returned
  `{"status":"ok"}`, and `/api/arranger/status` reported stopped transport,
  no active preview, and no backend error. Inspection inside the container
  confirmed the deployed live recognizer accepts chord notes alone and emits
  no bass inversion.
- **untested:** no physical FR-4X MIDI or accompaniment audio was exercised.
- **observed:** owner rejected chord-only recognition because an accordion bass
  onset is an important early cue before the chord button arrives.

## Gate

Stop after the software gate. Do not claim hardware or listening acceptance,
and do not commit or push without owner approval.
