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
                                         |       |
                                         |       +-> built-in audible POC (computer only)
                                         |
                                         +------ diagnostics
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

P0 contains diagnostics and the explicit keyboard chord source. An experimental
computer-only vertical slice can also render an original fixed pattern through
the default host route using `aplay`. Its transport advances by an absolute
integer audio-frame position, so buffers do not accumulate sleep-based drift.

The demo is not the future validated style loader, tick-based planner,
dispatcher, FluidSynth path, or FR-4X mapping. It changes no host settings and
does not claim any accordion or audio-latency evidence.
