"""Discovery, testing, and persistence for host ALSA accompaniment outputs."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from array import array
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from ostinato.computer_audio import DemoAudioConfig, open_pcm_sink

AUDIO_OUTPUT_SCHEMA_VERSION = 1


class AudioOutputError(RuntimeError):
    """An audio output could not be discovered, tested, or persisted."""


@dataclass(frozen=True, slots=True)
class AudioOutputDevice:
    """One exact PipeWire sink or direct ALSA PCM identifier."""

    id: str
    name: str


def discover_alsa_outputs(
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[AudioOutputDevice]:
    """Return exact direct-hardware PCM routes reported by ``aplay -L``."""

    executable = shutil.which("aplay")
    if executable is None:
        raise AudioOutputError("aplay is not available in the service container")
    try:
        result = runner(
            [executable, "-L"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise AudioOutputError(
            f"could not list ALSA playback outputs: {error}"
        ) from error

    devices: list[AudioOutputDevice] = []
    lines = result.stdout.splitlines()
    for index, line in enumerate(lines):
        if not line or line[0].isspace():
            continue
        identifier = line.strip()
        if not identifier.startswith("plughw:"):
            continue
        descriptions: list[str] = []
        for following in lines[index + 1 :]:
            if following and not following[0].isspace():
                break
            description = following.strip()
            if description:
                descriptions.append(description)
        label = " · ".join(descriptions[:2]) or identifier
        devices.append(AudioOutputDevice(identifier, label))
    return devices


def discover_pipewire_outputs(
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[AudioOutputDevice]:
    """Return exact playback nodes from the mounted host PipeWire session."""

    executable = shutil.which("pw-cli")
    if executable is None:
        raise AudioOutputError("pw-cli is not available in the service container")
    try:
        result = runner(
            [executable, "ls", "Node"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise AudioOutputError(f"could not list PipeWire outputs: {error}") from error

    nodes: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("id "):
            if current is not None:
                nodes.append(current)
            current = {}
            continue
        if current is None or " = " not in stripped:
            continue
        key, raw_value = stripped.split(" = ", 1)
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            continue
        if isinstance(value, str):
            current[key] = value
    if current is not None:
        nodes.append(current)

    devices: list[AudioOutputDevice] = []
    for node in nodes:
        name = node.get("node.name")
        if node.get("media.class") != "Audio/Sink" or name is None:
            continue
        description = node.get("node.description", node.get("node.nick", name))
        devices.append(
            AudioOutputDevice(
                id=f"pipewire:{name}",
                name=f"Host desktop · {description}",
            )
        )
    return devices


def discover_audio_outputs() -> list[AudioOutputDevice]:
    """Combine desktop-session sinks and direct ALSA routes when available."""

    devices: list[AudioOutputDevice] = []
    errors: list[str] = []
    for discover in (discover_pipewire_outputs, discover_alsa_outputs):
        try:
            devices.extend(discover())
        except AudioOutputError as error:
            errors.append(str(error))
    if not devices:
        raise AudioOutputError("; ".join(errors) or "no audio outputs were discovered")
    return devices


def play_output_test(device: str) -> None:
    """Play a bounded C-major chime through one already discovered route."""

    config = DemoAudioConfig(sample_rate=48_000, chunk_frames=480)
    duration_frames = config.sample_rate * 3 // 5
    samples = array("h")
    frequencies = (261.6256, 329.6276, 391.9954)
    for frame in range(duration_frames):
        elapsed = frame / config.sample_rate
        attack = min(1.0, elapsed * 30)
        release = max(0.0, 1.0 - (elapsed / 0.6))
        value = sum(
            math.sin(math.tau * frequency * elapsed) for frequency in frequencies
        )
        sample = round(6_000 * attack * release * value / len(frequencies))
        samples.extend((sample, sample))
    if sys.byteorder != "little":
        samples.byteswap()
    sink = open_pcm_sink(config, device)
    try:
        sink.write(samples.tobytes())
    finally:
        sink.close()


def default_audio_output_path() -> Path:
    configured = os.environ.get("OSTINATO_STATE_DIRECTORY")
    directory = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".local" / "state" / "ostinato"
    )
    return directory / "audio-output.json"


class AudioOutputStore:
    """Atomically persist one user-selected, discovered output identifier."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_audio_output_path()

    def load(self) -> dict[str, object] | None:
        if not self.path.exists():
            return None
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise AudioOutputError(
                f"could not read audio output settings: {error}"
            ) from error
        if not isinstance(value, dict):
            raise AudioOutputError("audio output settings must be a JSON object")
        if value.get("schema_version") != AUDIO_OUTPUT_SCHEMA_VERSION:
            raise AudioOutputError("unsupported audio output settings schema")
        return {str(key): item for key, item in value.items()}

    def save(self, device: AudioOutputDevice) -> dict[str, object]:
        value: dict[str, object] = {
            "schema_version": AUDIO_OUTPUT_SCHEMA_VERSION,
            "output_mode": "host_analog_audio",
            "device": device.id,
            "name": device.name,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                text=True,
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump(value, stream, indent=2, sort_keys=True)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)
        except OSError as error:
            raise AudioOutputError(
                f"could not save audio output settings: {error}"
            ) from error
        return value


class AudioOutputService:
    """Validate output choices against current discovery and run bounded tests."""

    def __init__(
        self,
        store: AudioOutputStore | None = None,
        *,
        discover: Callable[[], Sequence[AudioOutputDevice]] = discover_audio_outputs,
        test: Callable[[str], None] = play_output_test,
    ) -> None:
        self._store = store or AudioOutputStore()
        self._discover = discover
        self._test = test

    def devices(self) -> list[AudioOutputDevice]:
        devices = list(self._discover())
        if len({device.id for device in devices}) != len(devices):
            raise AudioOutputError("ALSA reported duplicate playback identifiers")
        return devices

    def saved_device(self) -> str | None:
        value = self._store.load()
        device = value.get("device") if value is not None else None
        return device if isinstance(device, str) else None

    def select(self, identifier: str) -> dict[str, object]:
        device = self._find(identifier)
        return self._store.save(device)

    def test(self, identifier: str) -> None:
        self._find(identifier)
        try:
            self._test(identifier)
        except Exception as error:
            raise AudioOutputError(f"audio test failed: {error}") from error

    def snapshot(self) -> dict[str, object]:
        devices = self.devices()
        saved = self.saved_device()
        available_ids = {device.id for device in devices}
        return {
            "devices": [asdict(device) for device in devices],
            "selected": saved,
            "available": saved in available_ids if saved is not None else False,
        }

    def _find(self, identifier: str) -> AudioOutputDevice:
        return next(
            (device for device in self.devices() if device.id == identifier),
            None,
        ) or self._unknown(identifier)

    @staticmethod
    def _unknown(identifier: str) -> AudioOutputDevice:
        raise AudioOutputError(f"audio output is not currently available: {identifier}")
