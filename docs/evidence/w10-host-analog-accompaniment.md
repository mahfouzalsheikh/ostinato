# W10 — Host analog accompaniment output

## Outcome

The web arranger now renders computer-generated stereo PCM instead of
sequencing accompaniment MIDI back to the FR-4X. The accordion remains a MIDI
input and its own analog output remains connected directly to the mixer.
Ostinato's selected computer or USB-audio analog output connects to a separate
mixer input.

## Automated evidence

- `AudioOutputService` accepts and persists only an exact identifier returned
  by current PipeWire or `aplay -L` discovery.
- The web service exposes discovery, bounded output test, and save endpoints;
  arranger start remains disabled until an available output is saved.
- The saved route is restored only if the same identifier is still reported.
- The arranger owns an `aplay --device <identifier>` PCM stream and no longer
  constructs `MidiArrangerOutput` in the web application.
- Hardware-free tests inject discovery and playback boundaries, so they do not
  imply that an ALSA device or loudspeaker was exercised.

## Observed environment

On 2026-08-28, read-only discovery inside the running container reported
playback devices for:

- `HDA Intel PCH` device 0, described by ALSA as `92HD95 Analog`;
- `ThinkPad USB-C Dock Gen2 USB Au` device 0, described as `USB Audio`.

PipeWire also reported `EDIFIER R1700BTs` as the current Bluetooth sink. These
names are observations from this host, not application defaults. The UI
displays exact `pipewire:<node.name>` identifiers for desktop/Bluetooth sinks
and `plughw:CARD=...,DEV=...` identifiers for direct hardware.

After mounting only the host's `pipewire-0` session socket into the rebuilt
container, `pw-cli` observed the built-in, EDIFIER Bluetooth, and USB-C dock
sinks. A bounded test stream targeting the exact EDIFIER node returned HTTP
200 and `pw-cat` exited successfully. This proves that the stream opened and
drained; whether it was audible and acceptable remains a human observation.

## Hardware gate

Status: **pending**.

1. Open **Audio output** in the web arranger.
2. Select the PCM route physically connected to the mixer.
3. Use **Play test chord** and confirm the chord is audible on the intended
   mixer channel.
4. Save, play bass/chord buttons, and verify Modern Tango and Classic Waltz,
   including intro and ending.
5. Record any underruns, output-open errors, subjective level/balance issues,
   and end-to-end latency. No acoustic or rehearsal claim is made yet.

## Safety boundary

The FR-4X analog signal is never captured or relayed by Ostinato. Ostinato
generates accompaniment audio only. The MIDI wizard's optional output remains
available for the browser's visual-keyboard simulator, but the arranger does
not send accompaniment MIDI to the accordion.
