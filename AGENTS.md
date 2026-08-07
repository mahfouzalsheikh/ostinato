# Project Ostinato agent contract

Read `project-ostinato-codex-execution-plan.md` before making project changes.

## Scope and gates

- Work one named milestone at a time and stop at its human gate.
- Preserve unrelated worktree changes.
- Never invent FR-4X channels, chord encodings, ALSA port names, audio device
  names, SoundFont paths, GPIO assignments, or proprietary file semantics.
- Hardware-dependent evidence must be marked `observed`, `untested`, or
  `pending`; tests must not imply that hardware was exercised.
- Keep the FR-4X analog audio on its direct mixer path. Ostinato generates only
  accompaniment audio.

## Commands

```bash
export PIPENV_VENV_IN_PROJECT=1
pipenv sync --dev
pipenv run ostinato --help
pipenv run ostinato doctor
pipenv run ostinato keyboard --keys 'zagxgq'
pipenv run scripts/run-checks.sh
```

Run `scripts/run-checks.sh` for the complete local software check suite. Do not
use `sudo` or install system packages without explicit user approval.

## Engineering rules

- Target Python 3.12+ and keep CI-safe tests independent of MIDI/audio hardware.
- Store clock time in integer nanoseconds and musical positions in integer
  ticks in later milestones.
- Keep event planning separate from dispatch and use absolute deadlines based
  on `time.monotonic_ns()`.
- Put milestone evidence in `docs/evidence/` and distinguish automated,
  observed, subjective, and pending claims.
