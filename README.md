# Project Ostinato

Project Ostinato is a Linux proof of concept for a live arranger driven by a
Roland FR-4X V-Accordion. The accordion's analog audio remains connected
directly to the mixer; the computer produces accompaniment only.

The repository currently implements milestone **P0** plus a hardware-free
computer-keyboard chord source and an experimental audible arranger demo. The
demo turns explicit keyboard chord choices into an original modern-tango
pattern through the computer's default audio output. FR-4X MIDI recording and
recognition deliberately wait for representative hardware captures.

## Quick start

Python 3.12 and Pipenv are required. The locked environment does not install
system packages:

```bash
export PIPENV_VENV_IN_PROJECT=1
pipenv sync --dev
pipenv run ostinato --help
pipenv run ostinato doctor
pipenv run scripts/run-checks.sh
```

Without installing the package, development commands can use:

```bash
PYTHONPATH=src python3 -m ostinato --help
PYTHONPATH=src python3 -m ostinato doctor
```

`doctor` only reads host state. Missing hardware and optional tools are
reported as `MISSING` or `UNTESTED`; they do not make the command fail. Use
`--json` for machine-readable output.

To exercise chord input without the FR-4X:

```bash
pipenv run ostinato keyboard
```

To hear the built-in computer-only modern tango (requires `aplay`):

```bash
pipenv run ostinato keyboard --play
pipenv run ostinato keyboard --play --tempo 96
```

While it is running, use `-` to slow down and `+` (or `=`) to speed up in
5-BPM steps. Press `i` for a four-measure ensemble intro and `o` to arm a
four-measure ending at the next bar.

See the [computer-only testing guide](docs/computer-only-testing.md) for the key
layout and scripted mode.

## Docker

On a native Linux Docker host, the Compose setup can expose the host USB bus
and ALSA devices without running a fully privileged container:

```bash
docker compose build
docker compose run --rm ostinato doctor
docker compose run --rm --entrypoint lsusb ostinato
```

Raw USB passthrough grants broad access to host USB devices. Read the
[Docker and USB guide](docs/docker.md) for the security boundary, reconnect
behavior, direct-ALSA audio path, and narrower ALSA-only option.

## Documentation

- [How the system works](docs/architecture.md)
- [Physical and USB/audio connections](docs/connections.md)
- [Pipenv development guide](docs/development.md)
- [Computer-only testing](docs/computer-only-testing.md)
- [Docker and USB passthrough](docs/docker.md)
- [Style format design contract](docs/style-format.md)

## System preparation

See [scripts/bootstrap-ubuntu.sh](scripts/bootstrap-ubuntu.sh) for a dry-run
package list. It prints commands by default and changes nothing. Run its
printed commands yourself after reviewing them.

Copy the examples in `config/` before entering machine-specific names. Do not
commit personal device names or an unverified FR-4X mapping as shared defaults.

## Current boundary

- Implemented: OST-001 through OST-003 (P0 software slice).
- Pending hardware: FluidSynth playback/endurance observation and FR-4X capture.
- Available without accordion hardware: explicit computer-keyboard chord-state
  input and an experimental built-in accompaniment through the default host
  audio route.
- Intentionally absent: FR-4X chord recognition, the production style
  loader/planner/dispatcher and FluidSynth path, UI, and Pi services.

The complete milestone sequence and acceptance criteria are in
`project-ostinato-codex-execution-plan.md`.
