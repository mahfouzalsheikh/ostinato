# P4 engine evidence

**Milestone:** P4 — Transport and minimal arranger vertical slice
**Slice:** Experimental computer-only audible POC
**Captured:** 2026-08-09
**Result:** Partial software slice passes; P4 and hardware acceptance remain pending

## Automated

The hardware-free keyboard source can feed normalized chord states to a small
built-in PCM renderer. The renderer creates an original tango-nuevo-inspired
pattern in 4/4, explicitly grouped as 1.5+1.5+1 beats. Its six procedural parts
are bass, piano, reed/bandoneon-like stabs, drums, auxiliary percussion, and
backing strings. It has a four-measure orchestrated intro plus a
next-bar-quantized four-measure ending that stops after its final accent. The
renderer advances from an absolute integer frame position, emits signed 16-bit
stereo PCM, and is deterministic for a given chord and position. Live tempo
changes retain the current beat position across transport segments.

Automated tests cover silence without a chord, exact frame advancement,
deterministic PCM, distinct output after root/quality changes, transport reset,
continuous tempo changes, bounded tempo controls, keyboard-event forwarding,
4/4 and 1.5+1.5+1 meter contracts, continuous 3-3-2 pattern definitions, pulse
wraparound, four-stage ensemble orchestration, intro-to-main and
ending-to-stopped transitions, section controls, deterministic non-repeating
drum noise, mastered output level, and CLI delegation. The complete local suite
passes:

| Command | Result |
| --- | --- |
| `pipenv run pytest` | PASS — 40 tests |
| `pipenv run ruff check .` | PASS |
| `pipenv run ruff format --check .` | PASS |
| `pipenv run mypy src tests` | PASS |

These tests render buffers in memory. They do not open audio or MIDI hardware.
A non-CI performance check rendered four seconds of the six-part main pattern
in 2.57 seconds on the current host, peaking at 11,264 with no clipped samples.

## Observed

Interactive pseudo-terminal smoke runs selected C major and streamed through
the host's default `aplay` route. A tempo-control run reported continuous
changes from 120 to 115, 120, and 125 BPM and quit cleanly without an `aplay`
error. A later A-minor run completed the full two-bar modern-tango phrase at
120 BPM; an in-memory level check found a peak of 12,795 and no clipped samples
across 192,000 stereo frames. After the all-3-3-2 and section-control update, a
compressed 240-BPM live run accepted intro and ending controls and exited
without an `aplay` error. An in-memory intro/main/ending render reached the
`stopped` state with the same 12,795 peak and no clipped samples across 960,000
interleaved samples. Acoustic audibility, subjective style, output level,
latency, xrun behavior, SoundFont, MIDI-device, and FR-4X behavior were not
observed. After the six-part/four-measure update, a live 240-BPM run accepted
the complete intro and ending sequence without an `aplay` error. Its matching
nine-second in-memory section render reached `stopped`, peaked at 11,617, and
had no clipped samples across 864,000 interleaved samples. A combined 13 seconds
of main and section audio rendered in 7.17 seconds on the current host.
After replacing the tonal snare/shaker oscillators with shaped deterministic
noise and adding soft-limited master gain, a four-second A-minor render measured
−2.3 dBFS peak and −16.3 dBFS RMS with no hard-clipped samples. A corresponding
live 120-BPM stream opened and exited without an `aplay` error.

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
The "modern tango" description is an implementation intent rather than a
subjective acceptance claim. The procedural sounds are intentionally a simple
audibility harness, not a candidate final sound set.
