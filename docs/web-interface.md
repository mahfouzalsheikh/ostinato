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

## Connect MIDI

1. Open **Input from accordion** and select an exact name reported by ALSA/RtMidi.
2. Optionally select **Output from simulator**. This is the port that receives
   browser key and button presses; do not select a destination you do not
   intend to control.
3. Choose **Apply connections**. The service remembers a requested port during
   a disconnect and tries to reopen that exact name if it returns.
4. Watch the raw event stream before assigning musical meaning.

No port is selected automatically. A port disappearing or failing is reported
in the interface and does not silently switch to another device.

## Map the 37-key piano surface

The visual keyboard needs two observed values:

- the one-based MIDI input channel carrying the right-hand piano events;
- the MIDI note number produced by the physical leftmost key in the current
  instrument setup.

The browser stores these values in local storage. Incoming note-on/note-off
events in the resulting 37-note range animate the piano keys. To use the
surface as a controller, also select a simulator output channel. The leftmost
note and output channel determine the raw messages sent by pointer presses.

These settings are user observations, not shared project defaults. Register,
transpose, orchestration, or instrument-setting changes can invalidate them.

## Train the 120-button surface

The FR-4X offers several left-hand layouts, so the initial UI uses neutral row
and column positions rather than naming chord or bass semantics.

1. Choose **Learn**.
2. Click one visual button.
3. Press the intended physical button once.
4. The next incoming note-on signature (channel and note) becomes that visual
   button's browser-local binding.

Learned buttons animate on matching note events and send the learned signature
through the selected output when clicked. **Clear bindings** removes all such
browser-local data.

This single-event learner is a visualization aid, not the production chord
mapper. A physical chord button may produce clusters, controls, mode-dependent
messages, or overlapping events. H1 recordings are still required before
those events can be assigned stable musical meaning.

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
| `WS /ws/midi` | Status, input/output events, and real-time commands |

The API is intentionally local and unauthenticated in this milestone.
