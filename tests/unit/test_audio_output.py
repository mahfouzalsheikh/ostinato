from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ostinato.audio_output import (
    AudioOutputDevice,
    AudioOutputError,
    AudioOutputService,
    AudioOutputStore,
    discover_alsa_outputs,
    discover_pipewire_outputs,
)


class AudioOutputDiscoveryTests(unittest.TestCase):
    def test_uses_only_exact_identifiers_reported_by_aplay(self) -> None:
        listing = """null
    Discard all samples
default:CARD=PCH
    HDA Intel PCH, Analog
    Default Audio Device
sysdefault:CARD=PCH
    HDA Intel PCH, Analog
plughw:CARD=PCH,DEV=0
    HDA Intel PCH, Analog
    Hardware device with all software conversions
"""

        with patch("ostinato.audio_output.shutil.which", return_value="/usr/bin/aplay"):
            devices = discover_alsa_outputs(
                runner=lambda *args, **kwargs: subprocess.CompletedProcess(
                    args[0], 0, stdout=listing, stderr=""
                )
            )

        self.assertEqual(
            devices,
            [
                AudioOutputDevice(
                    "plughw:CARD=PCH,DEV=0",
                    "HDA Intel PCH, Analog · "
                    "Hardware device with all software conversions",
                ),
            ],
        )

    def test_discovers_exact_pipewire_sinks_including_bluetooth(self) -> None:
        listing = """\
id 47, type PipeWire:Interface:Node/3
    node.description = "Built-in Audio Analog Stereo"
    node.name = "alsa_output.pci.analog-stereo"
    media.class = "Audio/Sink"
id 68, type PipeWire:Interface:Node/3
    node.description = "EDIFIER R1700BTs"
    node.name = "bluez_output.CC_14_BC_B3_AD_EC.1"
    media.class = "Audio/Sink"
id 82, type PipeWire:Interface:Node/3
    node.description = "Built-in Audio Analog Stereo"
    node.name = "alsa_input.pci.analog-stereo"
    media.class = "Audio/Source"
"""

        with patch(
            "ostinato.audio_output.shutil.which", return_value="/usr/bin/pw-cli"
        ):
            devices = discover_pipewire_outputs(
                runner=lambda *args, **kwargs: subprocess.CompletedProcess(
                    args[0], 0, stdout=listing, stderr=""
                )
            )

        self.assertEqual(
            devices,
            [
                AudioOutputDevice(
                    "pipewire:alsa_output.pci.analog-stereo",
                    "Host desktop · Built-in Audio Analog Stereo",
                ),
                AudioOutputDevice(
                    "pipewire:bluez_output.CC_14_BC_B3_AD_EC.1",
                    "Host desktop · EDIFIER R1700BTs",
                ),
            ],
        )


class AudioOutputServiceTests(unittest.TestCase):
    def test_persists_only_a_currently_discovered_exact_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AudioOutputStore(Path(directory) / "audio-output.json")
            device = AudioOutputDevice("plughw:CARD=Dock,DEV=0", "Dock Analog")
            service = AudioOutputService(store, discover=lambda: [device])

            saved = service.select(device.id)

            self.assertEqual(saved["output_mode"], "host_analog_audio")
            self.assertEqual(service.saved_device(), device.id)
            self.assertIs(service.snapshot()["available"], True)

    def test_rejects_a_stale_or_invented_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = AudioOutputService(
                AudioOutputStore(Path(directory) / "audio-output.json"),
                discover=lambda: [],
            )

            with self.assertRaises(AudioOutputError):
                service.select("plughw:CARD=Missing,DEV=0")


if __name__ == "__main__":
    unittest.main()
