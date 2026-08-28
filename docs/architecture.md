# Architecture

## Safety boundary

The FR-4X analog output goes directly to the mixer. Ostinato receives MIDI and
generates accompaniment through a separate synthesizer/audio path. A computer,
synthesizer, or control-display failure therefore cannot remove the performed
accordion voice.

## Runtime model

```text
FR-4X MIDI -> raw MIDI service -> WebSocket -> browser accordion surface
                   |                            |
                   |                            +-> explicit/user-trained mapping
                   +<------- simulator MIDI ----+
                   |
                   +-> capture/verified mapping --+
                                                    |
computer keyboard -> explicit mapping --------------+-> chord state -> planner -> dispatcher -> synth
                                                    |       |
                                                    |       +-> built-in audible POC (computer only)
                                                    |
                                                    +------ diagnostics
```

The real-time web service selects only exact names returned by the MIDI
backend. A callback timestamps raw messages with `time.monotonic_ns()` and
hands them to bounded per-browser queues on the asyncio event loop. WebSocket
clients receive raw bytes plus neutral message fields. Browser-generated MIDI
is validated before reaching the selected output. Port discovery and reconnect
monitoring do not contain an FR-4X name, channel, note range, or chord encoding.

The display is an observer/simulator and does not own accompaniment playback.
Its WebSocket path is best-effort UI telemetry, not the future event dispatcher
or a timing acceptance result.

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
computer-only vertical slice can also render an original modern-tango pattern
through the default host route using `aplay`. The 4/4 bar is grouped as
1.5+1.5+1 beats and orchestrated across procedural bass, piano, reed, drums,
auxiliary percussion, and backing strings. Its transport advances by an
absolute integer audio-frame position, so buffers do not accumulate sleep-based
drift. Its POC-only section state supports an immediate four-measure intro and
a four-measure ending quantized to the next bar; the ending enters a stopped
state after its final accent.

This audible harness writes mastered raw PCM directly to `aplay`. It creates no
MIDI output messages and therefore has no instrument or percussion channels.
Its noise-shaped procedural drum voices are separate from the later FluidSynth
and SoundFont output design.

The web surface and demo are not the future validated style loader, tick-based planner,
dispatcher, FluidSynth path, or FR-4X mapping. It changes no host settings and
does not claim any accordion or audio-latency evidence.
