# Project Ostinato maintenance plan

This plan describes the current Dockerized web arranger. It replaces the
historical build sequence and is the required context for future project work.

## Product boundary

Ostinato turns live left-hand MIDI from a Roland FR-4X V-Accordion into
accompaniment audio while visualizing both accordion keyboards in a browser.
The accordion's own analog audio remains on its direct mixer path. Ostinato
generates accompaniment audio only and sends no arranger sequence back to the
FR-4X.

The maintained product includes:

- a guided MIDI input/output setup wizard with saved role detection;
- exact learned MIDI fingerprints for six accordion-controlled arranger
  actions, without guessed FR-4X messages;
- real-time 39-key piano and 120-button Stradella visualization;
- a backend-owned arranger with style-shaped intro/main/ending, two one-bar
  Fill Ins, chord-aware monophonic section solos, sync, fixed tempo, and
  left-hand tempo following;
- fourteen built-in four-bar styles with genre-profiled open-sample SFZ racks,
  plus sampled General MIDI rendering for custom styles and 105 deduplicated,
  grouped host-local KORG imports;
- an advanced custom-style designer with editable instrumentation, mix,
  register, articulation, meter, phrase length, and live unsaved preview;
- explicit PipeWire/Bluetooth or ALSA accompaniment-output selection;
- Docker deployment with USB, ALSA, and desktop PipeWire access; and
- hardware-free deterministic tests and a procedural audio fallback.

## Non-negotiable safety rules

- Never invent FR-4X channels, chord encodings, ALSA names, PipeWire sink names,
  SoundFont paths, or proprietary style semantics.
- Hardware observations must be marked `observed`, `untested`, or `pending`.
  Automated tests must not imply that physical hardware was exercised.
- Preserve the FR-4X analog-audio path. Ostinato owns accompaniment audio only.
- Persist only explicitly selected or wizard-detected machine values.
- Keep the service bound to loopback by default; changing network exposure is a
  separate security decision.
- Do not bundle proprietary Yamaha, Roland, Korg, or community style files.
  Record provenance and compatible licenses for every distributed style or
  sound asset.

## Runtime architecture

```text
FR-4X USB MIDI
      │
      ▼
MIDI service ──► role profile ──► causal harmony + tempo tracking
      │                                  │
      └────────► WebSocket UI            ▼
                                 live arranger state
                                          │
                                          ▼
                         sfizz rack / FluidSynth renderer
                                          │
                                          ▼
                              selected host audio sink
```

The live MIDI callback performs bounded normalization and queueing. Arranger
state, harmony, transport, and audio ownership stay in the backend so a browser
reload cannot stop accompaniment. Musical positions use integer ticks and
runtime scheduling derives from monotonic time.

The main implementation modules are:

| Module | Responsibility |
| --- | --- |
| `web_server.py` | FastAPI routes, WebSocket lifecycle, static application |
| `realtime_midi.py` | MIDI discovery, input events, simulator output |
| `midi_detection.py` / `midi_profile.py` | Guided role detection and persistence |
| `performance_controls.py` | Learned MIDI fingerprint matching and action routing |
| `arranger.py` | Live harmony, tempo, transport, and preview state |
| `computer_audio.py` | Style vocabulary, PCM sink, fallback renderer |
| `soundfont_audio.py` | Sampled General MIDI accompaniment |
| `sfz_audio.py` | Genre-profiled open-sample built-in style racks |
| `audio_output.py` | PipeWire/ALSA discovery, testing, and saved output |
| `style_designer.py` | Custom-style validation and atomic persistence |
| `web_static/` | Browser controls and accordion visualization |

## State and deployment

Compose stores machine state in the `ostinato-state` volume. Current documents
are the MIDI profile (including learned controls), selected audio output, and
custom styles. They are written
atomically and restored only when the corresponding device is still available.

The container uses the explicit MuseScore General HQ SoundFont path installed by
the Debian package and retains TimGM6mb only as an explicit A/B reference.
Every built-in instead uses the build-pinned sfizz library and an explicitly
configured open SFZ genre profile; asset versions, checksums, licenses, and
paths are recorded in `docs/style-library-sources.md`.
Desktop and Bluetooth sinks are reached through the mounted user
PipeWire socket; direct hardware uses `/dev/snd`. Raw USB access is intentionally
bounded by Compose device rules rather than a privileged container.

## Development checks

```bash
export PIPENV_VENV_IN_PROJECT=1
pipenv sync --dev
pipenv run ostinato --help
pipenv run ostinato doctor
pipenv run ostinato keyboard --keys 'zagxgq'
pipenv run scripts/run-checks.sh
```

The complete check script runs Python tests, browser JavaScript tests, Ruff
format/lint, and strict mypy. Tests must stay independent of MIDI and audio
hardware. Use dependency injection and fake synth/MIDI boundaries.

For a deployed change:

1. run the full local check suite;
2. rebuild with `docker compose up -d --build`;
3. wait for the Compose health check;
4. verify the affected API and browser flow;
5. stop any preview or transport started for verification; and
6. record automated, deployed-software, observed, subjective, and pending claims
   accurately in the current milestone evidence.

## Change gates

Work on one named milestone at a time and stop at its human gate. Typical gates:

- **software gate:** tests, typing, formatting, health, API, and browser checks;
- **hardware gate:** actual FR-4X/USB/host-audio behavior observed by the user;
- **listening gate:** style realism, levels, timing, and playability accepted by
  the performer; and
- **release gate:** requested commit/push after the relevant human gate.

Preserve unrelated worktree changes. Use reversible cleanup where possible and
never replace saved machine-specific state with guessed defaults.

## Current evidence and provenance

- `docs/evidence/w44-learned-midi-performance-controls.md` records the exact
  fingerprint-learning design, excluded musical/bellows signals, automated
  verification, and pending physical FR-4X gate.
- `docs/evidence/w43-chord-detection-reliability.md` records the quiet-window
  chord assembly, bounded hard deadline, mask-based classification, and local
  performance diagnostics.
- `docs/evidence/w42-korg-library-groups-and-deduplication.md` records the full
  official primary-package inventory, actual Pa80-converter compatibility
  probes, exact live-payload deduplication, the 105-style grouped UI catalog,
  and deployed software verification.
- `docs/evidence/w41-korg-arabic-world-expansion.md` records the official
  Turkish/Arabic/World and World-package conversion, the forty-five-style UI
  catalog, rejected incompatible meters and converter failures, and deployed
  software verification.
- `docs/evidence/w40-korg-volume-2-library.md` records the official
  `Styl-v02.zip` import, the expanded sixteen-style UI catalog, the explicit
  melodic-anchor fallback for styles without a CV1 bass part, and deployed
  software verification.
- `docs/evidence/w39-korg-live-library.md` records the read-only local style
  catalog, UI/timeline integration, explicit CV1 chord policy, deployed live
  scheduler, and non-silent real-FluidSynth verification for all eight styles.
- `docs/evidence/w38-korg-pa80-reference-import.md` records the official
  converter reference workflow, strict per-Chord-Variation SMF importer, all
  eight locally imported `Styl-v01` styles, and fixed-pitch offline audio
  references. Source-chord/transposition semantics and live integration remain
  gated.
- `docs/evidence/w37-korg-styl-v01-inspection.md` records the real official
  `Styl-v01.zip` extraction, the catalog-only legacy `KORF` probe, and the
  confirmed absence of embedded Standard MIDI chunks. Musical decoding and
  playback remain gated on a MIDI export or verified native semantics.
- `docs/evidence/w36-korg-style-import-foundation.md` records the local-only
  KORG asset workflow, secure package inspection, vendor-neutral style model,
  and synthetic marker-based MIDI import. Its real-source and playback gates
  are pending.
- `docs/evidence/w35-local-midi-arrangement-enrichment.md` records the
  deduplicated local-library analysis and richer accompaniment implementation;
  `docs/midi-library-analysis.md` contains the aggregate findings and limits.
- `docs/evidence/w34-chord-aware-section-solos.md` records the deterministic
  chord-tone solo model for intros, endings, and both Fill Ins.
- `docs/evidence/w33-style-research-orchestra-timeline.md` records the
  all-style orchestration review, clarinet/trumpet and guitar-rack upgrades,
  and shared designer/live arrangement timeline.
- `docs/evidence/w32-style-sections-fill-ins.md` records essential-instrument
  balancing, section-specific arrangement material, and the two quantized Fill
  In controls.
- `docs/evidence/w31-open-sfz-builtins.md` records the expansion of the accepted
  open-sample approach to all built-in styles and its pending listening gate.
- `docs/evidence/w30-open-sfz-waltz.md` records the accepted dedicated
  open-sample Waltz prototype.
- `docs/evidence/w29-hq-soundfont.md` records the prior GM-library experiment
  whose listening gate was rejected.
- `docs/evidence/w28-causal-harmony-prediction.md` records the latest automated
  verification boundary for bass-and-melody harmony prediction.
- `docs/evidence/w27-chord-only-harmony.md` records the rejected chord-only
  behavior that W28 supersedes.
- `docs/evidence/w26-current-version-cleanup.md` records the preceding cleanup
  and deployed verification boundary.
- `docs/evidence/w25-licensed-groove-style-pack.md` records the retained style
  pack and provenance boundary.
- `docs/style-library-sources.md` records the external groove references,
  transformations, attribution, and libraries evaluated but not bundled.
- `README.md` is the canonical product overview and operating guide.
- Topic-specific details live in `docs/architecture.md`, `docs/connections.md`,
  `docs/docker.md`, `docs/web-interface.md`, `docs/development.md`, and
  `docs/computer-only-testing.md`.

## Deferred work

- physical latency and endurance measurements on the final performance route;
- further arrangement variations after performer listening;
- authenticated KORG NTT/key behavior or higher Chord Variation selection if
  verified semantics become available;
- experimental direct `.STY` decoding only from verified format semantics;
- authenticated remote access if the web service is ever exposed beyond
  loopback; and
- Raspberry Pi, GPIO, enclosure, and kiosk work after the laptop version passes
  its hardware and listening gates.
