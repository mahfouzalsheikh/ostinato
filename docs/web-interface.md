# Real-time web/MIDI interface

The web interface is a live raw-MIDI monitor and simulator foundation. It uses
native browser Web Components and a FastAPI/WebSocket service; no frontend
build step is required. The visual surface follows the official FR-4X physical
counts of [37 right-hand keys and 120 left-hand buttons](https://www.roland.com/global/products/fr-4x/specifications/).

It does **not** contain a default FR-4X MIDI mapping. The instrument supports
multiple bass/chord and free-bass layouts, and the project has not completed
the H1 representative capture gate.

## Run locally

With the locked Pipenv environment installed:

```bash
pipenv run ostinato web
```

Open <http://127.0.0.1:8765>. The host command binds only to loopback unless an
explicit `--host` value is supplied. For the Docker workflow, see
[docker.md](docker.md).

## Connect and detect MIDI

Choose **Set up MIDI** to open the three-step setup wizard:

1. Select an exact ALSA/RtMidi input name and, optionally, an output for the
   browser simulator.
2. Start and stop capture while playing only the requested physical role:
   right-hand treble, left-hand bass buttons, then left-hand chord buttons.
3. Review the ranked observed channels. A channel that appeared in multiple
   phases has lower confidence and remains editable before saving.

The detector does not contain FR-4X channel defaults. The labels come from the
guided performance and the candidates come only from received note-on events.
It detects channel activity and observed note ranges; it does not infer chord
encodings or the physical position of individual left-hand buttons.

Saving writes a versioned profile on the service. On later starts, Ostinato
reconnects only when those exact saved port names are available. A missing port
is reported and never replaced with a different device automatically. The
input can still reconnect when an optional saved output is absent. Run the
wizard again after changing the instrument's MIDI transmission setup.

## Visualize the 37-key piano surface

The saved treble channel and observed note set drive the piano directly; there
is no separate mapping form. The visual keyboard has the physical 37-key F-to-F
pitch-class shape. Ostinato selects an F-aligned 37-note MIDI window containing
the observed treble notes and centers incomplete samples within that window.
This prevents an arbitrary lowest sampled note from shifting every displayed
pitch. Playing the physical lowest and highest keys during setup removes octave
ambiguity.

Browser piano presses send the corresponding inferred MIDI note on the observed
treble channel through the selected output. A fixed velocity is used for this
provisional simulator.

## Visualize the 120-button Stradella surface

The left surface implements the FR-4X **2 Bass Rows** table: counterbass,
fundamental bass, major, minor, dominant seventh, and diminished rows across 20
circle-of-fifths columns. It is not a free-bass projection. The exact displayed
labels and order follow Roland's reference-manual table.

Incoming notes on the detected bass channel illuminate the central occurrence
of both possible Stradella bass-row buttons. When a recognized chord is active, a
bass note a major third above its root is shown in that chord column's
counterbass row. The FR-4X transmits pitch, not a unique physical button ID, so
a standalone pitch that exists as both a fundamental and counterbass remains
inherently ambiguous; the interface marks both candidates instead of claiming
that one physical switch was observed.

Incoming chord-channel notes are grouped over a short 12 ms window and matched
as major, minor, dominant-seventh, or diminished note sets. The documented
single-note **D-Mode** codes are supported as well. A recognized chord lights
one root/quality button. Browser presses replay only exact bass notes or chord
clusters that have already been observed during the current page session.

This milestone targets the standard two-bass-row Stradella mode. The FR-4X also
offers several three-bass-row Stradella variants; those require an explicit
layout choice before their different row geometry can be displayed safely.

## Real-time and safety boundary

- MIDI callbacks are timestamped with integer monotonic nanoseconds.
- Each browser has a bounded queue; when a slow display fills its queue, the
  oldest display event is discarded rather than blocking MIDI input.
- Browser output accepts only complete, validated MIDI messages.
- A browser disconnect or output-port change releases notes that the web
  simulator started, preventing those lifecycle events from being abandoned.
- The WebSocket display is best-effort and is not the accompaniment scheduler.
- No browser timing result is accepted as MIDI/audio latency evidence.
- The web service has no authentication or TLS. Keep the default loopback bind
  unless a separate trusted-network boundary is in place.
- FR-4X analog audio continues directly to the mixer. It never enters this web
  service or the accompaniment container.

## HTTP and WebSocket boundary

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Container/readiness check |
| `GET /api/midi/status` | Available and selected ports |
| `PUT /api/midi/ports` | Select exact input/output names or disconnect |
| `POST /api/midi/send` | Send one validated raw MIDI message |
| `POST /api/midi/detect` | Rank channels from three labeled note captures |
| `GET /api/midi/profile` | Load the saved, versioned detection profile |
| `PUT /api/midi/profile` | Validate and atomically save a reviewed profile |
| `DELETE /api/midi/profile` | Remove the saved profile |
| `WS /ws/midi` | Status, input/output events, and real-time commands |

The API is intentionally local and unauthenticated in this milestone.
