# W15 — Stable tempo and sampled arranger engine

## Milestone boundary

Address reported lag, automatic-tempo instability, and the tonal limitations
of the Python oscillator renderer. This milestone keeps the existing five
original arrangements and selected host PCM route. It does not claim parity
with a commercial arranger or introduce proprietary style data.

## Implemented behavior

- The arranger monitor now sleeps until the next chord or sync deadline rather
  than polling permanently every 5 ms.
- Automatic tempo requires three consistent normalized intervals, rejects
  isolated samples outside a 12% inlier band, uses a median window, and limits
  later movement to three BPM per accepted observation.
- Docker selects the package-provided TimGM6mb SoundFont explicitly and renders
  it through libfluidsynth into the existing stereo PCM output.
- The native synth gain is calibrated against the complete arrangements rather
  than FluidSynth's conservative default. Harmless note-off responses for
  voices that have already ended no longer stop the audio worker.
- Each style has its own GM palette spanning sampled bass, comping instrument,
  reed or lead, strings, and percussion. Harmony changes invalidate sustained
  melodic voices at the next 10 ms audio chunk.
- The PipeWire stream requests a 20 ms application buffer instead of 40 ms.
  Bluetooth transport and speaker buffering remain outside Ostinato.
- The original procedural renderer remains the CI-safe fallback when no
  SoundFont is configured.

## Evidence

- **observed:** the container contains TimGM6mb at the configured path; Debian
  package metadata identifies the file as GPL-2.
- **automated:** all five sampled renderers configure their palettes, emit
  bass/harmony/drum events, follow chord changes, and retain four-bar
  intro/ending contracts using a fake native-synth boundary.
- **observed:** an in-container native smoke test loaded the SoundFont and
  produced non-silent PCM for all five styles. After gain calibration, two
  seconds of each main pattern measured 13,764–26,511 peak and 2,807–4,713 RMS
  on signed 16-bit PCM without clipping.
- **observed:** before calibration, audio did reach the selected EDIFIER
  Bluetooth sink, but a live monitor capture measured only 150 peak on signed
  16-bit PCM. The selected host sink was also at 19% volume. This explained the
  reported effective silence without changing the user's host volume.
- **automated:** native rendering consumed 18–25 ms of CPU time per second of
  generated audio on this host, compared with roughly 700 ms for the prior
  procedural renderer. This is a software benchmark, not an xrun guarantee.
- **automated:** tempo tests cover timing outliers, combined bass/chord pulses,
  style normalization, and deadline-aware monitor waits.
- **pending:** acoustic latency, Bluetooth delay, xrun behavior, musical
  balance, and commercial-arranger comparison under actual performance.

## Safety boundary

The accordion's analog voice remains on its direct mixer path. Ostinato still
generates accompaniment only. No FR-4X MIDI mapping, host audio identifier, or
unobserved SoundFont path was added.
