# P4 engine evidence

**Milestone:** P4 — Transport and minimal arranger vertical slice
**Slice:** Experimental computer-only audible POC
**Captured:** 2026-08-09
**Result:** Partial software slice passes; P4 and hardware acceptance remain pending

## Automated

The hardware-free keyboard source can feed normalized chord states to a small
built-in PCM renderer. The renderer creates an original fixed drums, bass, and
chord pattern, advances from an absolute integer frame position, emits signed
16-bit stereo PCM, and is deterministic for a given chord and position. Live
tempo changes retain the current beat position across transport segments.

Automated tests cover silence without a chord, exact frame advancement,
deterministic PCM, distinct output after root/quality changes, transport reset,
continuous tempo changes, bounded tempo controls, keyboard-event forwarding,
and CLI delegation. The complete local suite passes:

| Command | Result |
| --- | --- |
| `pipenv run pytest` | PASS — 31 tests |
| `pipenv run ruff check .` | PASS |
| `pipenv run ruff format --check .` | PASS |
| `pipenv run mypy src tests` | PASS |

These tests render buffers in memory. They do not open audio or MIDI hardware.

## Observed

Interactive pseudo-terminal smoke runs selected C major and streamed through
the host's default `aplay` route. A tempo-control run reported continuous
changes from 120 to 115, 120, and 125 BPM and quit cleanly without an `aplay`
error. Acoustic audibility, output level, latency, xrun behavior, SoundFont,
MIDI-device, and FR-4X behavior were not observed.

## Pending

- Run `pipenv run ostinato keyboard --play` in the user's desktop session and
  confirm that the default host route produces the demonstration arrangement.
- Assess whether the explicit quality/root key workflow is useful for the POC.
- Complete H1 before implementing any production FR-4X mapping or recognition.
- Implement the validated style schema, MIDI style loader, tick transport,
  planner, dispatcher, note lifecycle, and FluidSynth output required for P4.
- Complete H2 before making live latency or endurance claims.

## Subjective

Sound quality, responsiveness, and musical usefulness are pending user review.
The procedural sounds are intentionally a simple audibility harness, not a
candidate final sound set.
