# Architecture

## Safety boundary

The FR-4X analog output goes directly to the mixer. Ostinato receives MIDI and
generates accompaniment through a separate synthesizer/audio path. A computer,
synthesizer, or control-display failure therefore cannot remove the performed
accordion voice.

## Runtime model

```text
FR-4X MIDI -> capture/verified mapping --+
                                         |
computer keyboard -> explicit mapping ---+-> chord state -> planner -> dispatcher -> synth
                                                              ^              |
                                                              |              v
                                                       transport clock  diagnostics
```

All input sources converge on a `ChordState`: root pitch class, quality,
optional bass pitch class, confidence, source event identifiers, and monotonic
recognition time. The computer keyboard produces this explicitly for testing.
The FR-4X path will produce it only through rules derived from labeled captures.

Input recording/replay, mapping, transport, planning, dispatch, and synthesis
are separate modules. The planner will combine chord state with a validated
style and emit immutable normalized MIDI events for a bounded lookahead window.
The dispatcher will own output, timing, and active-note accounting. FluidSynth
turns dispatched MIDI into accompaniment audio.

Start, stop, tempo, section, fill, ending, and panic controls eventually update
the engine through a command boundary. Displays observe status but do not own
the playback lifetime, so restarting a UI cannot interrupt accompaniment.

## Timing contract

Later playback code will represent time as integer nanoseconds and musical
position as integer ticks. Deadlines derive from a fixed transport epoch and
absolute tick position, never from a prior wake-up time. Tempo changes create a
new continuous epoch/position segment.

## Current implementation boundary

P0 contains diagnostics and the explicit keyboard chord source. It does not
open MIDI ports, start audio, schedule accompaniment, or change host settings.
The keyboard source therefore displays normalized changes but makes no sound.
