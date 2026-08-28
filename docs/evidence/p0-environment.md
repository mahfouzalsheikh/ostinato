# P0 environment evidence

**Milestone:** P0 — Repository and environment  
**Tasks:** OST-001 through OST-003  
**Captured:** 2026-07-31  
**Result:** Software slice passes; hardware acceptance remains pending

## Automated

Host inspection reported:

- Ubuntu 24.04.4 LTS (Noble), Linux `7.0.0-28-generic`, x86-64;
- Python 3.12.3 at `/usr/bin/python3`;
- Debian/Ubuntu package management (`apt`) is the documented bootstrap path;
- ALSA utilities `aconnect`, `amidi`, `aplay`, and `arecord` are on `PATH`;
- PipeWire utility `pw-cli` is on `PATH`; and
- FluidSynth is not on `PATH`.

An isolated `.venv` is managed through Pipenv. `Pipfile.lock` pins runtime and
development dependencies, and `pipenv sync --dev` installs the editable local
package. No system package or global Python environment was changed.

Verification results:

| Command | Result |
| --- | --- |
| `pipenv verify` | PASS — lock is current |
| `pipenv sync --dev` | PASS — locked dependencies installed |
| `pipenv run pytest` | PASS — 20 tests |
| `pipenv run ruff check .` | PASS |
| `pipenv run ruff format --check .` | PASS — 24 files formatted |
| `pipenv run mypy src tests` | PASS — 14 source files |
| `pipenv run ostinato --help` | PASS — exit 0 |
| `pipenv run ostinato doctor --json` | PASS — exit 0 |
| `pipenv run ostinato keyboard --keys 'zaxg q'` | PASS — scripted chord changes and quit |
| Interactive `ostinato keyboard` in a pseudo-terminal | PASS — raw keys, clear, and quit |

Tests inject command and device results; they do not require or claim access to
audio/MIDI hardware.

The keyboard simulator creates explicit normalized chord states and does not
claim to recognize or reproduce FR-4X MIDI behavior.

## Observed

No physical audio or MIDI behavior was observed during this milestone. The
Codex execution environment did not expose `/dev/snd/seq`, did not report an
ALSA playback/capture device, and could not connect to the user's PipeWire
session. Those results are recorded as `UNTESTED`, not as proof that the host
lacks working audio or MIDI hardware.

## Pending

- Confirm the intended audio interface and MIDI interface/connection.
- Run `ostinato doctor` in the user's normal desktop session with the interface
  and FR-4X connected; retain its JSON output.
- Install FluidSynth and a legally usable test SoundFont after reviewing
  `scripts/bootstrap-ubuntu.sh`.
- Select the real FluidSynth audio driver/device and SoundFont path; none is
  assumed in shared configuration.
- Play a known MIDI file through FluidSynth for 30 minutes and record xruns and
  the exact settings. This is the remaining OST-004/P0 hardware acceptance.
- Capture and label representative FR-4X MIDI data. This is human gate H1 and
  blocks production input mapping/chord rules.

## Subjective

No musical or performance assessment was performed in P0.

## H0 status

Linux distribution, package-manager family, and Python version are confirmed.
The user must still confirm the actual audio/MIDI hardware names and that the
FR-4X analog audio is connected directly to the mixer rather than routed
through the computer.

## Gate decision

OST-001 through OST-003 are complete. OST-004 and H1 require user-controlled
hardware activity. Per the execution contract, implementation stops before P1
and does not invent an FR-4X event mapping.

## Docker packaging addendum — 2026-08-28

### Automated

A multi-stage Python 3.12 image and Linux Compose service now package the
locked runtime environment, ALSA utilities, FluidSynth, and `usbutils`.
Compose grants only ALSA and USB character-device classes rather than using a
fully privileged container.

| Command | Result |
| --- | --- |
| `docker compose config --quiet` | PASS |
| `docker compose build` | PASS |
| `docker compose run --rm ostinato --help` | PASS — exit 0 |
| `docker compose run --rm ostinato doctor` | PASS — exit 0 |
| `docker compose run --rm ostinato keyboard --keys zagxgq` | PASS — scripted chord changes and quit |
| `pipenv run scripts/run-checks.sh` | PASS — 40 tests, Ruff, format check, and mypy |

### Observed

On the Linux development host, `lsusb` in the Compose container enumerated the
same host USB controllers and attached peripherals exposed under
`/dev/bus/usb`. The container also accessed `/dev/snd/seq` and reported the
kernel ALSA sequencer client. No Roland/FR-4X USB identity or FR-4X MIDI port
was present in the captured output.

These observations prove the configured device mounts were active on this
host. They do not prove that the FR-4X transmitted MIDI or that accompaniment
audio played correctly.

### Pending

- Connect the FR-4X and confirm its verified identity appears in container
  `lsusb`, `aconnect -l`, or `amidi -l` output.
- Disconnect and reconnect the FR-4X while the service is running and observe
  whether the replacement device node and ALSA port become available.
- Exercise the container's direct-ALSA output and record the selected device;
  no PipeWire desktop-session socket is mounted by the initial setup.
- Measure latency and xruns separately. Container enumeration is not timing or
  endurance evidence.
