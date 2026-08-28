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

Whether the host's default ALSA route is usable inside the container remains a
hardware-assisted check. Desktop PipeWire routing is not mounted into this
container; direct ALSA device access is the initial container path.

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
