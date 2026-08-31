# Docker on a Linux host

The image packages Ostinato, its locked Python runtime dependencies, ALSA
utilities, FluidSynth, and `usbutils`. Compose exposes the Linux host's ALSA
devices and USB device filesystem to the container. It does not route the
FR-4X analog audio through Ostinato: keep that signal connected directly to
the mixer as described in [connections.md](connections.md).

## Start the web service

Docker Engine and the Compose plugin must already be installed on the Linux
host. From the repository root:

```bash
docker compose up --build --detach
docker compose ps
```

Open <http://127.0.0.1:8765>. The service publishes only on host loopback by
default and its health check probes `/api/health`. To use another host port:

```bash
OSTINATO_WEB_PORT=8080 docker compose up --build --detach
```

The interface has no login or TLS termination. Deliberately exposing it to the
LAN requires an explicit bind override and an appropriate trusted-network
boundary:

```bash
OSTINATO_WEB_BIND=0.0.0.0 docker compose up --build --detach
```

Stop the service with `docker compose down`. See
[web-interface.md](web-interface.md) for port selection and mapping behavior.
The guided MIDI profile and selected accompaniment audio output are stored in
the Compose-managed `ostinato-state` volume and survive normal
container replacement and `docker compose down`. Running
`docker compose down --volumes` also deletes those saved settings.

## Diagnose and run one-off commands

The service can stay running while separate one-off containers perform the
read-only diagnostics:

```bash
docker compose run --rm ostinato doctor
docker compose run --rm --entrypoint lsusb ostinato
```

`doctor` is read-only. Seeing a USB device in `lsusb`, `aconnect`, or `amidi`
shows that Linux exposed it to the container; it does not prove FR-4X mapping,
latency, audio quality, or reconnect behavior.

Run the hardware-free scripted check without opening an audio device:

```bash
docker compose run --rm ostinato keyboard --keys zagxgq
```

For the interactive keyboard demo, Compose already allocates a terminal:

```bash
docker compose run --rm ostinato keyboard
```

The audible demo uses ALSA through the passed `/dev/snd` tree:

```bash
docker compose run --rm ostinato keyboard --play
```

The web interface lists host desktop sinks reported by PipeWire, including
connected Bluetooth audio, plus direct `plughw` routes reported by `aplay -L`.
It lets the performer play a bounded test chord and saves only the selected
identifier. It never substitutes another device when the saved route is
missing.

Compose mounts `${XDG_RUNTIME_DIR}/pipewire-0` read/write at a private
container path. Run Compose from the logged-in desktop user's session so
`XDG_RUNTIME_DIR` identifies the PipeWire session. The mount exposes audio
routing control and playback to the container; it does not expose unrelated
files from the runtime directory. Direct ALSA remains available as a fallback.

## Sampled accompaniment engines

### Genre-profiled open-sample built-ins

The image builds sfizz 1.2.3 from its pinned BSD-2-Clause source revision and
downloads checksum-pinned open SFZ libraries during the build. Compose passes
the exact sampler and instrument paths; Ostinato refuses a partial rack rather
than searching the filesystem or silently substituting an instrument. The
extracted sample payload is about 6.2 GB. The libraries, versions, checksums,
attribution, and licenses are recorded in
[style-library-sources.md](style-library-sources.md).

Built-in Classic Waltz uses separate piano, pizzicato bass, flute, cello,
violin, and brushed-drum synths. Its piano chords are slightly staggered, winds
are monophonic, strings sustain across the measure, and every harmony change
cuts stale melodic voices immediately. The other built-ins select explicit
profiles from the same accepted instruments plus Shinyguitar's
acoustic/electric archtop, Black and Blue Basses' fingered/picked five-string
basses, and Virtuosity Drums' live kit and General MIDI percussion. Guitar and
ensemble chord voices are staggered instead of triggered as one sample-block
attack. Custom styles continue to use their user-selected General MIDI
instruments.

Render the former GM Waltz and the open-sample rack at matched musical content
and calibrated levels without opening an audio device:

```bash
mkdir -p /tmp/ostinato-waltz-comparison
docker compose run --rm \
  --volume /tmp/ostinato-waltz-comparison:/comparison \
  ostinato waltz-compare --output /comparison
```

The two 48 kHz WAV files and `manifest.json` make a listening comparison
repeatable. Peak/RMS measurements verify level alignment and clipping only;
they do not measure realism.

To compare every genre rack against the former GM renderer:

```bash
mkdir -p /tmp/ostinato-sfz-comparison
docker compose run --rm \
  --volume /tmp/ostinato-sfz-comparison:/comparison \
  ostinato sfz-compare --output /comparison
```

Pass `--style funk_pocket`, for example, for one pair. A cold non-Waltz rack
takes roughly 3–5 seconds to load in the current container; steady rendering is
at least 3.65 times real time in the hardware-free benchmark. This is software
throughput evidence, not an acoustic latency result.

### General MIDI custom styles and fallback

The runtime package installs FluidSynth, the Debian
`musescore-general-soundfont` package, and the legacy
`timgm6mb-soundfont` package. Compose passes the package-owned
`/usr/share/sounds/sf3/MuseScore_General_Full.sf3` path explicitly through
`OSTINATO_SOUNDFONT`; Ostinato does not search for or silently choose another
file. Debian documents MuseScore General HQ as a GM-compatible, MIT-licensed
library with separate ensemble samples. Its package copyright and source
metadata remain installed in the image. TimGM6mb is retained under GPL-2 for
explicit legacy comparisons.

When this configured file is present, custom styles use native FluidSynth
voices from the curated acoustic-piano, acoustic-guitar, flute, and General MIDI
drum palette. The web style designer saves editable template,
meter, phrase length, instrument, register, articulation, tempo, drum, and mix
choices in the existing persistent state volume. Its optional catalog also
includes electric and acoustic basses, additional guitars and keys, strings,
harp, and winds. Custom instrument styles require this configured SoundFont.
Without the variable, the deterministic procedural PCM renderer remains
available for development and hardware-free tests of the built-in styles.

### Reproducible SoundFont A/B comparison

The comparison command renders the same fixed C-Am-F-G7 progression through
both packaged libraries for every built-in style:

```bash
mkdir -p /tmp/ostinato-soundfont-comparison
docker run --rm \
  --volume /tmp/ostinato-soundfont-comparison:/comparison \
  project-ostinato:local \
  soundfont-compare --output /comparison
```

The output contains 28 matched WAV files plus `manifest.json`, which records
peak and RMS levels, clipped-sample counts, and frame counts. Pass a style such
as `--style classic_waltz` for one pair. These objective measurements catch
level and clipping regressions; they do not prove that a library sounds more
realistic.

To temporarily run the service with the legacy library:

```bash
OSTINATO_SOUNDFONT=/usr/share/sounds/sf2/TimGM6mb.sf2 \
OSTINATO_SOUNDFONT_NAME=TimGM6mb \
docker compose up -d --force-recreate
```

Running the normal Compose command restores MuseScore General HQ as the default.

## USB and device-access boundary

The Compose service deliberately has access to these Linux character-device
classes:

- major `116`: ALSA MIDI and audio devices under `/dev/snd`;
- major `189`: raw USB devices under `/dev/bus/usb`.

The wildcard cgroup rules allow device minors created after the container
starts, which is important when a USB device disconnects and reconnects with a
new bus address. The container is **not** privileged, but it runs as root
because raw USB nodes often are not writable by an ordinary host user.

Mounting the complete USB bus grants access to every host USB device, not just
the FR-4X. If that boundary is too broad, remove the `/dev/bus/usb` volume and
the `c 189:*` rule. Ostinato's planned MIDI path uses ALSA, so `/dev/snd` is the
important mapping after the host kernel has recognized the accordion. A more
restrictive raw-USB setup requires a verified device identity and host udev
permissions; this repository does not invent those values.

Device passthrough is supported only with a native Linux Docker Engine. Docker
Desktop on macOS or Windows runs containers in a virtual machine and cannot use
these Linux host paths as written. Rootless Docker can also reject or limit
device mappings.

The relevant Docker contracts are the Compose service
[`devices` and `device_cgroup_rules` fields](https://docs.docker.com/reference/compose-file/services/)
and the Engine's
[runtime device-access controls](https://docs.docker.com/engine/containers/run/#runtime-privilege-and-linux-capabilities).

## Development checks in the image

The runtime image intentionally omits test and lint dependencies. Run the
complete development suite on the host with the project's supported Pipenv
workflow:

```bash
pipenv run scripts/run-checks.sh
```

Container build and configuration validation are separate packaging checks:

```bash
docker compose config --quiet
docker compose build
docker compose run --rm ostinato --help
```
