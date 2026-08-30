# Project Ostinato

Project Ostinato is a Linux proof of concept for a live arranger driven by a
Roland FR-4X V-Accordion. The accordion's analog audio remains connected
directly to the mixer; the computer produces accompaniment only.

The repository currently implements milestone **P0**, a hardware-free
computer-keyboard chord source, an experimental fourteen-style audible arranger,
and a real-time web/MIDI surface. The guided setup saves reviewed input roles;
FR-4X recording and production chord recognition still wait for representative
hardware captures.

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
and ALSA devices without running a fully privileged container. Start the live
web service and open <http://127.0.0.1:8765>:

```bash
docker compose up --build --detach
docker compose run --rm ostinato doctor
docker compose run --rm --entrypoint lsusb ostinato
```

Raw USB passthrough grants broad access to host USB devices. Read the
[Docker and USB guide](docs/docker.md) for the security boundary, reconnect
behavior, direct-ALSA audio path, and narrower ALSA-only option.

For host development without Docker:

```bash
pipenv run ostinato web
```

The web page also provides backend-owned arranger controls for fourteen
arrangements. Alongside six original tango, waltz, bossa, swing, and polka
patterns, an attributed CC BY 4.0 groove pack adds soul, funk, soft pop,
country, reggae, samba, cha-cha, and blues options. Docker uses the installed GPL-licensed TimGM6mb
SoundFont through native FluidSynth; hosts without a configured SoundFont
retain the procedural PCM fallback. Each style has a four-bar phrase,
orchestrated intro and ending, rhythmic fills, combined bass/chord tempo
tracking, and left-hand sync. Choose **Audio output**
to test and save an exact host PipeWire sink (including Bluetooth) or direct
ALSA route. Ostinato synthesizes accompaniment on that route for an analog
connection to the mixer; the accordion keeps its own direct analog mixer
connection and is used only as arranger MIDI input. See the
[real-time web interface guide](docs/web-interface.md).

## Documentation

- [How the system works](docs/architecture.md)
- [Physical and USB/audio connections](docs/connections.md)
- [Pipenv development guide](docs/development.md)
- [Computer-only testing](docs/computer-only-testing.md)
- [Docker and USB passthrough](docs/docker.md)
- [Real-time web/MIDI interface](docs/web-interface.md)
- [Style library sources and licenses](docs/style-library-sources.md)
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
  input, experimental built-in accompaniments through a selected host audio
  route, and the web surface with fake-backend automated tests.
- Available with user-selected ports: raw MIDI monitoring/output, a 39-key
  piano surface, a two-bass-row Stradella display, and fourteen computer-generated
  accompaniment styles through an explicitly selected host audio output.
- Intentionally absent: hardware-validated FR-4X chord recognition, a general
  style-v1 loader, program/register automation, authenticated remote access,
  and Pi services.

The complete milestone sequence and acceptance criteria are in
`project-ostinato-codex-execution-plan.md`.
