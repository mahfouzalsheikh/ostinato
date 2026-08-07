# Project Ostinato

## Codex execution plan for an FR-4X live arranger

**Status:** Validated and ready for incremental execution  
**Primary instrument:** Roland FR-4X V-Accordion  
**Development target:** Linux laptop  
**Deployment target:** Raspberry Pi 5 stage appliance  
**Plan version:** 1.0  
**Date:** 2026-07-31

> An ostinato is a repeating musical pattern. The name fits an arranger that continuously transforms accompaniment patterns around the performer's live chords.

---

## 1. Validation verdict

The proposed project is technically viable and correctly prioritizes a Linux proof of concept before Raspberry Pi hardware work. Its strongest architectural decision is keeping the FR-4X analog audio on a direct path to the mixer while the computer generates only accompaniment. That preserves the accordion sound if the arranger fails and avoids adding computer latency to the performed voice.

The original roadmap is approved with these changes:

1. **Do not make latency acceptance a prerequisite for chord-recognizer development.** Once representative MIDI fixtures exist, chord recognition and offline style-engine work can proceed without audio hardware. Latency remains a hard gate for declaring the laptop POC successful and purchasing/finalizing Pi hardware.
2. **Use absolute-time scheduling.** Derive every event deadline from a fixed transport epoch and integer musical ticks using `time.monotonic_ns()`; never advance the clock by repeatedly adding sleep durations.
3. **Keep event planning separate from event dispatch.** The planner may look ahead by a configurable interval. A small dispatcher emits due MIDI events. Chord and section changes invalidate only future, not-yet-dispatched events.
4. **Define the style schema before building the full scheduler.** The manifest must state section length, loop behavior, reference harmony, track roles, and note-transformation policies. Otherwise harmonization behavior will become implicit and difficult to test.
5. **Treat chord recognition as an FR-4X mapping problem first.** Do not start with a generic keyboard chord detector until recordings show whether the accordion sends chord notes, dedicated chord channels, bass/chord combinations, or program/control messages for the configured mode.
6. **Separate automated, hardware-assisted, and subjective acceptance.** Codex can implement and verify software tests locally; the user must perform accordion capture, acoustic latency recording, and musical-feel acceptance.
7. **Use percentile-based timing criteria.** Record median, p95, p99, and maximum onset latency and scheduler lateness. The under-12-ms target must state which statistic passes; this plan uses p99 under 12 ms, with no sample above 20 ms during the controlled latency run.
8. **Defer Django, Angular, a database, proprietary-style import, GPIO, and enclosure work.** None belongs in the laptop POC's critical path.

### Feasibility boundaries

- Python is appropriate for MIDI mapping, musical state, pattern transformation, orchestration, and the POC scheduler. FluidSynth and the audio stack perform synthesis and audio processing in native code.
- A general-purpose Linux system cannot guarantee hard real-time behavior. The goal is bounded, measured soft real-time performance with sufficient headroom.
- A 128-sample quantum at 48 kHz is 2.67 ms for one buffer period, not total end-to-end latency. Interface buffering, MIDI transport, synthesis, scheduling, and conversion must be measured together.
- A laptop result does not predict Raspberry Pi performance. The Pi repeats the complete latency, thermal, and endurance suite.

---

## 2. Product boundary

### POC must deliver

- Configurable ALSA MIDI input discovery and reconnect behavior.
- Timestamped FR-4X event recording and deterministic fixture replay.
- Verified recognition of major, minor, dominant-seventh, and diminished chords observed in captured data.
- Stable transport with integer ticks and quantized transitions.
- One original style with drums, bass, chord/pad, intro, main, fill, and ending.
- Start, stop, panic, tempo, fill, and section controls from a terminal or keyboard.
- Reproducible latency and endurance reports.
- A documented go/no-go decision for Raspberry Pi migration.

### POC explicitly excludes

- Angular, Django, DRF, databases, and network-dependent controls.
- Physical controls, GPIO, touchscreen, enclosure, and custom power electronics.
- Roland sample extraction or dependency on proprietary style formats.
- A large style library or polished production sounds.
- Routing the FR-4X analog audio through the computer.

---

## 3. Execution model for Codex

### 3.1 Working rules

Codex should execute one milestone at a time and stop at every named human gate.

For each coding milestone, Codex must:

1. Inspect the repository, `AGENTS.md`, current branch, and uncommitted changes.
2. Preserve unrelated user changes and never reset or overwrite them.
3. Restate the milestone, assumptions, and files expected to change.
4. Implement the smallest vertical slice satisfying that milestone.
5. Run formatting, linting, type checks, and tests available for the affected code.
6. Update documentation, configuration examples, and the milestone evidence file.
7. Report changed files, commands run, results, limitations, and the next gate.
8. Stop if required hardware evidence or an undocumented musical decision is missing.

Do not silently invent FR-4X channels, SoundFont paths, ALSA port names, audio device names, chord encodings, GPIO pins, or proprietary file semantics.

### 3.2 Human gates

| Gate | User supplies | Codex resumes when |
| --- | --- | --- |
| H0 — Host details | Linux distribution/version, package manager, Python version, audio/MIDI hardware | Bootstrap assumptions are confirmed |
| H1 — MIDI capture | Representative FR-4X JSONL recordings and transmission settings | Fixtures contain labeled bass/chord/control examples |
| H2 — Latency capture | Two-channel audio recordings or measured onset data for tested buffer sizes | Results can be summarized reproducibly |
| H3 — Musical review | Notes from an actual rehearsal and any recorded failure cases | Response and transitions are accepted or defects are reproducible |
| H4 — Pi purchase/selection | Final Pi audio/MIDI interface and control hardware choices | Laptop POC decision gate passes |

### 3.3 Required repository evidence

Each milestone adds or updates an evidence file under `docs/evidence/`:

- `p0-environment.md`
- `p1-midi-mapping.md`
- `p2-latency.md`
- `p3-chord-recognition.md`
- `p4-engine.md`
- `p5-rehearsal.md`
- `pi-benchmark.md`

Evidence files distinguish:

- **automated:** produced by tests or scripts;
- **observed:** recorded from hardware diagnostics;
- **subjective:** performer assessment;
- **pending:** not yet verified.

---

## 4. Proposed repository

```text
project-ostinato/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── config/
│   ├── devices.example.yaml
│   └── performance.example.yaml
├── docs/
│   ├── architecture.md
│   ├── style-format.md
│   └── evidence/
├── recordings/
│   ├── README.md
│   └── labels.example.yaml
├── scripts/
│   ├── bootstrap-ubuntu.sh
│   └── run-checks.sh
├── styles/
│   └── poc-style/
│       ├── style.yaml
│       ├── intro.mid
│       ├── main-a.mid
│       ├── fill-a.mid
│       └── ending.mid
├── src/ostinato/
│   ├── cli.py
│   ├── domain.py
│   ├── midi_input.py
│   ├── midi_record.py
│   ├── midi_replay.py
│   ├── input_mapping.py
│   ├── chord_recognizer.py
│   ├── transport.py
│   ├── style_schema.py
│   ├── style_loader.py
│   ├── harmonizer.py
│   ├── planner.py
│   ├── dispatcher.py
│   ├── synth_output.py
│   ├── control.py
│   └── diagnostics.py
└── tests/
    ├── fixtures/
    ├── integration/
    └── unit/
```

Recommended initial developer tooling:

- Python 3.12 or newer;
- `mido`, `python-rtmidi`, `PyYAML`, and `pytest`;
- `ruff` for formatting and linting;
- `mypy` for type checking;
- FluidSynth plus ALSA and PipeWire/JACK command-line diagnostics.

Pin a supported Python range rather than an exact patch version. Commit the lock file if a locking tool is adopted.

---

## 5. Core technical contracts

### 5.1 Time and transport

- Store time in integer nanoseconds and musical position in integer ticks.
- Capture a transport epoch when playback starts.
- Calculate each deadline from `epoch + ticks_to_ns(position, tempo_map)`.
- Never calculate the next beat from the actual wake-up time of the previous beat.
- Record scheduler lateness as `actual_dispatch_ns - deadline_ns`.
- Support only constant tempo in the first vertical slice; add tempo-map semantics later.
- On tempo change, establish a new epoch/position segment without discontinuity.

### 5.2 Planner and dispatcher

- The planner produces immutable normalized MIDI events for a bounded lookahead window.
- Default lookahead begins at 20 ms but remains configurable and benchmarked.
- The dispatcher owns output emission and active-note accounting.
- Section and harmony changes take effect at explicit musical boundaries.
- Replanning cancels future events by generation identifier; already-dispatched note-ons still receive matching note-offs.
- Panic sends all-notes-off/all-sound-off on used channels and clears internal note state.

### 5.3 Chord state

Normalized chord state contains:

```text
root_pitch_class, quality, optional_bass_pitch_class,
confidence, source_event_ids, recognized_at_ns
```

- Start with only qualities demonstrated by fixtures.
- Preserve the last valid chord through releases unless the configured mapping proves a meaningful no-chord state.
- Coalescing delay is configuration, not a hidden constant.
- Every unrecognized cluster is serializable for later labeling.

### 5.4 Style format v1

The style manifest must include:

- schema version, name, default tempo, time signature, and MIDI ticks per quarter;
- section-to-MIDI-file mapping, length in bars, loop behavior, and legal next sections;
- track role, source channel, output channel, bank/program, level, pan, and mute;
- reference root and quality for pitched patterns;
- per-track transform policy: `fixed`, `drums`, `root_transpose`, or `chord_tone_map`;
- note-range limits and octave-wrap policy;
- transition quantization and fill destination behavior.

The first schema intentionally excludes advanced guitar modes, chord-scale rules, proprietary imports, and tempo maps.

### 5.5 Fixture format

Use JSON Lines with one metadata header followed by normalized messages. Each event includes schema version, monotonic offset in nanoseconds, MIDI bytes or normalized fields, port label, and optional human label. Fixtures use offsets rather than wall-clock timestamps so replay is deterministic.

---

## 6. Laptop POC milestones

### P0 — Repository and environment

**Codex tasks**

- Scaffold the repository and package.
- Add `AGENTS.md` containing this execution contract and project-specific commands.
- Add Ubuntu bootstrap instructions and example configuration.
- Implement `ostinato doctor` to report Python, MIDI ports, relevant audio devices, FluidSynth availability, and missing dependencies without changing the machine.
- Add CI-safe tests that do not require audio or MIDI hardware.

**User tasks**

- Confirm H0 host details.
- Install system packages when prompted; Codex must not assume permission to use `sudo`.
- Connect FR-4X audio directly to the mixer and configure MIDI OUT.

**Acceptance**

- `python -m ostinato --help` exits successfully.
- `pytest`, `ruff check`, `ruff format --check`, and `mypy` pass.
- `ostinato doctor` clearly distinguishes available, missing, and untested components.
- A known MIDI file plays through FluidSynth for 30 minutes with no observed xruns.

**Stop condition:** Stop at H1 if no representative FR-4X recording exists.

### P1 — MIDI probe, recorder, and replay

**Codex tasks**

- Implement port listing, selection by stable matching rules, timestamps, JSONL recording, clean shutdown, and reconnect behavior.
- Implement deterministic fixture replay and a summary by channel/message type/note/controller.
- Add fixture schema validation and synthetic test fixtures.
- Document a labeled capture protocol for treble, every bass root, major/minor/seventh/diminished chord buttons, overlaps, registers, controls, and expression.

**User tasks**

- Perform the labeled capture protocol on the actual FR-4X.
- Record the relevant FR-4X settings and identify mislabeled or ambiguous takes.

**Acceptance**

- A recording can be replayed with original timing, scaled timing, or immediate test timing.
- Malformed fixtures fail with actionable errors.
- The mapping evidence contains no unverified channel assumptions.
- Disconnect/reconnect does not crash the recorder and is represented in diagnostics.

**Stop condition:** Do not implement production chord rules from synthetic assumptions. Stop until H1 is complete.

### P2 — Latency harness and audio baseline

**Codex tasks**

- Add scripts/configuration to route live MIDI to FluidSynth at 48 kHz.
- Record exact buffer, period, driver, device, SoundFont, polyphony, and host-load settings.
- Provide an onset-analysis tool for two-channel WAV recordings, with manual override when automatic onset detection is unreliable.
- Produce CSV/Markdown summaries for median, p95, p99, maximum, and sample count.

**User tasks**

- Capture direct FR-4X and synthesized audio on separate channels for 256-, 128-, and, if stable, 64-sample settings.
- Repeat at idle and under representative load.
- Run the selected stable configuration for four hours while monitoring xruns.

**Acceptance**

- The measurement method is reproducible and its uncertainty is documented.
- Selected configuration: p99 onset difference under 12 ms, no sample over 20 ms in the controlled run, and zero xruns during the four-hour endurance run.
- If no configuration passes, evidence identifies the next component to isolate: MIDI adapter, interface/driver, audio graph, FluidSynth configuration, or host scheduling.

**Parallelism:** After H1, P3 unit work may proceed while H2 recording is pending. P4 may proceed in offline-render/test mode. P2 must pass before the laptop POC decision gate.

### P3 — FR-4X input mapper and chord recognizer

**Codex tasks**

- Convert captured events into typed input actions.
- Implement only chord qualities proven by captures.
- Implement configurable event clustering/coalescing and last-valid-chord behavior.
- Add table-driven tests for presses, releases, overlaps, rapid changes, expression, unrelated treble events, and malformed sequences.
- Emit diagnostics for recognized and unrecognized clusters.

**Acceptance**

- 100% of labeled canonical fixtures produce the expected normalized chord.
- No spurious chord appears in labeled rapid-transition fixtures.
- Recognition completion meets the measured transition budget for all fixtures.
- Every unknown event cluster is retained in diagnostic output rather than discarded silently.

### P4 — Transport and minimal arranger vertical slice

**Codex tasks**

- Implement transport, style-schema validation, MIDI parsing, planner, dispatcher abstraction, note lifecycle, harmonizer, start/stop/panic, and tempo controls.
- Create tests using a fake clock and in-memory MIDI sink.
- Create or accept one original four-bar POC style with drums, bass, and chord/pad tracks.
- Provide offline event rendering so musical output can be inspected without real-time hardware.

**Acceptance**

- Simulated four-hour playback has no accumulated clock error beyond integer rounding bounds.
- Event ordering is deterministic at multiple tempos.
- Every note-on has a note-off or is terminated by panic.
- Major and minor fixture changes produce expected transformed patterns.
- Style validation rejects ambiguous lengths, unsupported policies, and out-of-range MIDI data.
- Live four-hour playback completes with zero xruns after P2 establishes the audio baseline.

### P5 — Sections, controls, and rehearsal release

**Codex tasks**

- Add intro, main A, fill A, ending, and quantized transitions.
- Add terminal/keyboard controls for start, stop, tempo, fill, ending, and panic.
- Add per-track program, level, pan, and mute.
- Add health/status output without coupling UI lifetime to playback.
- Add a session report that captures version, configuration, underruns, scheduler-lateness percentiles, unrecognized chords, and control history.

**User tasks**

- Perform complete songs using the actual instrument and mixer/PA path.
- Record defects with approximate song position, tempo, chord, and requested section.
- Decide whether chord response, voicing, and transitions feel natural.

**Acceptance**

- A complete song can be performed without a trackpad.
- Transitions happen at documented boundaries.
- Closing/restarting the control display does not stop playback.
- Panic reliably silences active accompaniment.
- At least three rehearsals complete without crash, xrun, stuck note, or unexplained transition.
- H3 subjective acceptance is recorded.

---

## 7. Laptop-to-Pi decision gate

Proceed only when all conditions are true:

- FR-4X mapping and required instrument settings are documented and repeatable.
- Canonical chord fixtures pass with no spurious transitions.
- P2 latency and four-hour xrun criteria pass on the selected laptop configuration.
- One complete original style supports a realistic performance.
- Three rehearsals pass P5 acceptance.
- Scheduler and UI/control lifecycles are independent.
- Remaining risks are target hardware, packaging, thermal behavior, controls, content expansion, or sound quality—not an unresolved musical architecture defect.

If latency fails, isolate the hardware/audio path before rewriting the musical engine. If timing passes but the system feels unnatural, investigate chord-change policy, voicing, pattern design, and section quantization before buying faster hardware.

---

## 8. Raspberry Pi roadmap

### R0 — Target performance spike

- Install a minimal 64-bit OS and selected audio/MIDI interface.
- Run the unchanged POC package, style, fixtures, and SoundFont.
- Repeat P2 under realistic background services and inside the intended thermal setup.
- Record boot time, CPU, memory, temperature, throttling, latency percentiles, scheduler lateness, and xruns.

**Exit:** Laptop acceptance still passes with at least 30% CPU headroom during the stress style and no thermal throttling.

### R1 — Headless appliance

- Package arranger and synth as separate systemd services with explicit readiness and restart behavior.
- Add known-device selection, default configuration, watchdog/health reporting, and panic independent of the UI.
- Boot directly to a playable default style.

**Exit:** Twenty consecutive cold boots become playable predictably; synth or UI failure recovery does not require a terminal.

### R2 — Registrations and local control API

- Add versioned, atomically written configuration and registrations.
- Add a local command/event API separated from the scheduler.
- Test interrupted writes and rollback to a known-good configuration.

**Exit:** Saved setups survive reboot and simulated interrupted writes.

### R3 — Touch UI

- Add the Angular UI only now, with large controls and visible style, tempo, chord, section, beat, MIDI, temperature, and xrun health.
- Support kiosk startup and reconnection.

**Exit:** Repeated browser crash/reload has no audible effect.

### R4 — Physical and foot controls

- Add configurable, debounced buttons, encoder, footswitches, LEDs, and a dedicated panic path.
- Test double presses, holds, disconnects, and noisy contacts.

**Exit:** A full performance requires neither screen nor keyboard.

### R5 — Musical expansion

- Add variations, fills, breaks, chord qualities, better phrase/guitar transformations, style validation/import tools, and additional legally usable sounds.
- Preload samples and establish polyphony/voice-stealing policy.

**Exit:** Several distinct styles maintain consistent perceived levels and pass regression/endurance tests.

### R6 — Stage hardening

- Add cooling, throttling alarms, durable connectors, strain relief, controlled shutdown, power-loss resilience, watchdog, known-good fallback, backups, and restore instructions.
- Evaluate read-only/overlay storage only after write requirements are documented.

**Exit:** Repeated boot, power interruption, reconnect, high-temperature, and full-rehearsal tests require no developer recovery.

### R7 — Release candidate

- Freeze hardware revisions and supported style/config schemas.
- Produce a reproducible OS image/build process, operations manual, wiring guide, backup/restore procedure, troubleshooting guide, and spare-image strategy.
- Run several full-length dress rehearsals.

**Exit:** The performer explicitly accepts the appliance for a live performance.

---

## 9. Initial Codex backlog

Execute in this order unless a human gate blocks progress:

| ID | Task | Depends on | Owner | Verifiable output |
| --- | --- | --- | --- | --- |
| OST-001 | Inspect host/repo and record assumptions | — | Codex + user | H0 answers and baseline report |
| OST-002 | Scaffold package, checks, docs, and examples | OST-001 | Codex | Green local checks |
| OST-003 | Implement non-mutating `doctor` command | OST-002 | Codex | Diagnostic output/tests |
| OST-004 | Establish FluidSynth test playback | OST-003 | User + Codex | P0 evidence |
| OST-005 | Implement MIDI port listing/probe | OST-002 | Codex | Unit tests and live output |
| OST-006 | Implement JSONL recorder/schema | OST-005 | Codex | Valid synthetic recording |
| OST-007 | Implement deterministic replay/summary | OST-006 | Codex | Replay tests |
| OST-008 | Capture and label FR-4X set | OST-007 | User | H1 fixtures |
| OST-009 | Derive configurable FR-4X mapping | OST-008 | Codex | Mapping document/tests |
| OST-010 | Implement chord recognizer | OST-009 | Codex | P3 acceptance |
| OST-011 | Define and validate style schema v1 | OST-002 | Codex | Schema tests/docs |
| OST-012 | Implement fake-clock transport | OST-002 | Codex | Drift/tempo tests |
| OST-013 | Implement MIDI style loader/harmonizer | OST-010, OST-011 | Codex | Transformation tests |
| OST-014 | Implement planner/dispatcher abstraction | OST-012, OST-013 | Codex | Deterministic event tests |
| OST-015 | Implement note lifecycle/start/stop/panic | OST-014 | Codex | Cleanup tests |
| OST-016 | Build latency capture/analyzer | OST-004 | Codex | WAV/CSV report pipeline |
| OST-017 | Run latency and endurance suite | OST-016 | User + Codex | H2/P2 evidence |
| OST-018 | Integrate original POC style live | OST-015, OST-017 | Codex + user | P4 evidence |
| OST-019 | Add musical sections and controls | OST-018 | Codex | Transition tests |
| OST-020 | Conduct and assess three rehearsals | OST-019 | User + Codex | H3/P5 evidence |
| OST-021 | Issue Pi go/no-go decision | OST-020 | User + Codex | Signed decision record |

Tasks OST-011, OST-012, and OST-016 may run while H1 capture is pending. OST-010 and production harmonization rules may not.

---

## 10. First prompt to run in local Codex

Use this prompt from the directory where the repository should be created:

```text
Create the Project Ostinato Linux POC repository by executing milestone P0 and
tasks OST-001 through OST-003 from project-ostinato-codex-execution-plan.md.

Before editing:
1. Read the entire plan and any AGENTS.md files in scope.
2. Inspect the current directory, git status, operating system, Python version,
   and available commands. Do not install system packages or use sudo.
3. Ask only for information that materially blocks a safe implementation.

Implement the smallest complete P0 software slice, including the package,
configuration examples, tests, quality checks, README, AGENTS.md, and a
non-mutating `ostinato doctor` command. Hardware-dependent checks must report
UNTESTED or MISSING, not fail the unit-test suite. Do not implement the chord
recognizer, arranger engine, UI, or Pi services yet.

Run all applicable checks. Then update docs/evidence/p0-environment.md with
automated results and clearly marked pending hardware observations. Finish with
changed files, verification results, blockers, and the exact H0/H1 actions I
must perform next. Do not claim hardware behavior you did not observe.
```

---

## 11. Definition of project completion

Project Ostinato is stage-ready only when:

- it boots into a playable state predictably;
- direct FR-4X audio remains available if the arranger or UI fails;
- representative chord performances are recognized correctly;
- measured latency, scheduler lateness, thermal behavior, and xrun tests pass on final hardware;
- intros, variations, fills, breaks, and endings work at documented boundaries;
- beat-sensitive operations are available through physical or foot controls;
- UI failure and recovery are inaudible;
- power interruption, backup, restore, and known-good fallback are tested;
- several full dress rehearsals pass without developer intervention;
- all distributed styles, samples, and SoundFonts have recorded provenance and compatible licenses;
- the performer trusts the system for a live show.

---

## 12. Technical references

- [Roland FR-4X product information and manuals](https://www.roland.com/global/products/fr-4x/articles/)
- [FluidSynth audio-driver settings](https://www.fluidsynth.org/api/settings_audio.html)
- [PipeWire documentation](https://docs.pipewire.org/)
- [Python monotonic clock documentation](https://docs.python.org/3/library/time.html#time.monotonic_ns)

