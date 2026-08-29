# Architecture

## Safety boundary

The FR-4X analog output goes directly to the mixer. In the web arranger,
Ostinato generates accompaniment PCM on an explicitly selected host ALSA
output, which connects to a separate mixer input. The computer never captures
or relays the accordion's analog signal, and accompaniment MIDI is not sent
back to the FR-4X.

## Runtime model

```text
FR-4X USB MIDI -> raw MIDI service -> browser accordion/control surface
                       |      ^
                       |      +------- simulator MIDI
                       |
                       +-> reviewed input roles -> bass/chord pulse fusion
                                                   -> harmony/tempo/sync state
                                                   |
                                                   +-> style event renderer
                                                       -> native FluidSynth + SoundFont
                                                          (procedural PCM fallback)
                                                       -> selected host PCM output
                                                       -> mixer analog input

computer keyboard -> explicit chord mapping -> procedural PCM demo
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

Input mapping, arranger state, procedural rendering, and PCM-output ownership
are separate boundaries. The audio worker retains its own transport and
renders bounded stereo buffers; it does not depend on browser timing. Stop,
output failure, output change, and shutdown close the owned PCM stream.

Start, stop, intro, ending, style, sync, and panic controls update the web
arranger through an HTTP command boundary. Displays observe status
but do not own the playback lifetime, so restarting a UI does not interrupt
accompaniment. Fill and a general style-file engine remain pending.

## Timing contract

Later playback code will represent time as integer nanoseconds and musical
position as integer ticks. Deadlines derive from a fixed transport epoch and
absolute tick position, never from a prior wake-up time. Tempo changes create a
new continuous epoch/position segment.

## Current implementation boundary

The web service renders six proof-of-concept styles as stereo PCM. The Docker
runtime uses the package-provided TimGM6mb SoundFont through libfluidsynth;
hardware-free development retains the deterministic procedural fallback. It is
disabled until the performer selects an exact currently discovered PipeWire
sink or direct `plughw` route. A bounded C-major test verifies the same route
before rehearsal; the selection is atomically persisted and restored only when
that exact PCM identifier is still available. No ALSA card or device is a
shared default.

All styles use four-bar intros, varying four-bar main phrases, and four-bar
endings. Bass roles, comping, reeds, pads, accents, articulations, and
timekeeper patterns are independently declared instead of being generically
layered onto every genre. The web service fuses deduplicated attacks from the saved bass and
chord channels, then normalizes their movement against the selected style's
rhythmic spacing. Bass-note changes update the accompaniment inversion
immediately; new chord-note clusters are isolated from notes still held from
the preceding chord. Optional left-hand sync starts and stops from the same
activity stream. It is still a small hard-coded arranger rather than the future
validated style-v1 loader, and its musical sophistication is not claimed to
match a commercial hardware arranger.

The CLI `keyboard --play` harness still writes to the default `aplay` route;
the web service differs by requiring an explicit route. Automated tests do not
claim physical FR-4X behavior, acoustic latency, or musical acceptance; those
remain hardware and rehearsal gates.
