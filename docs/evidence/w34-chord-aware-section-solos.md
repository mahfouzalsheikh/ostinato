# W34 — chord-aware section solos

Status: software and deployed-software gates complete; performer listening gate
pending.

## Scope

Intro, Ending, Fill In 1, and Fill In 2 now feature a monophonic improvised
line instead of replaying a three-note chord stack. This does not change chord
recognition, transport quantization, the main accompaniment, or the FR-4X
analog-audio route.

## Musical behavior

- Each of the fourteen built-in styles defines two deterministic melodic
  contours in chord-tone degrees. The first shapes intros and Fill In 1; the
  more animated contour shapes endings and Fill In 2.
- Chord-tone degrees are resolved against the live major, minor, dominant
  seventh, or diminished chord. A chord change therefore redirects subsequent
  notes without model inference, network access, or non-deterministic latency.
- Solo rhythms reuse each style's authored melodic-answer and harmonic
  landmarks, including its meter. Notes are shortened against the next attack
  to keep the feature line articulate and monophonic.
- The final Ending note is the current chord root. Main-section answer parts
  retain their existing voicing behavior.
- Built-in SFZ profiles keep their style-selected answer instrument, including
  violin, flute, trumpet, and clarinet. Classic Waltz's dedicated flute path
  implements the same solo contract. Custom styles use the selected Fill
  instrument through their existing sampled palette.

## Automated evidence

- Focused sampled/procedural tests: passed.
- Tests cover all fourteen styles, all supported chord qualities, monophonic
  feature attacks, distinct Fill 1/Fill 2 contours, Ending root resolution,
  and the dedicated Classic Waltz flute path.
- Complete local suite: `171 passed`.
- Ruff formatting/lint, strict mypy, browser tests, `git diff --check`, and
  `docker compose config --quiet`: passed.

## Deployed-software evidence

- The image rebuilt from source, the service was recreated, and Compose reached
  `healthy`; `/api/health` returned `{"status":"ok"}`.
- Offline renders inside the final container used the real sfizz sample racks
  and returned non-silent PCM with zero clipped samples: Modern Tango Intro
  (`-21.46 dBFS RMS`), Swing Foxtrot Fill 1 (`-21.12 dBFS RMS`), Alpine Polka
  Fill 2 (`-15.55 dBFS RMS`), and Classic Waltz Ending (`-25.45 dBFS RMS`).
- Final arranger state: `running=false`, `section=stopped`, style
  `modern_tango`, synthesis engine `sfizz · open sampled genre ensemble`, and no
  arranger error.

## Evidence boundary and human gate

- Physical FR-4X, mixer, amplifier, and speaker behavior: **untested**.
- Section-solo timing, chord alignment, instrumentation, and cadence behavior:
  **automated** at the renderer boundary.
- Musicality, realism, expressive fit, and balance on the physical performance
  route: **pending** performer listening.
