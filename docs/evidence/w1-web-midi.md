# W1 web/MIDI foundation evidence

**Milestone:** W1 — Real-time web/MIDI monitor and accordion simulator foundation  
**Captured:** 2026-08-28  
**Result:** Hardware-independent slice passes; FR-4X mapping remains at H1

This is a user-directed scope addition to the laptop POC. It does not mark the
later authenticated/control UI, arranger engine, or Raspberry Pi R3 milestone
complete.

## Automated

- Exact-name MIDI input/output selection rejects unavailable invented names.
- Fake MIDI ports exercise input callback fan-out, raw output validation,
  reconnect after disappearance, and actionable unavailable-output errors.
- FastAPI tests exercise health, static assets, status/selection, MIDI output,
  and the WebSocket command/error boundary.
- Static-surface tests assert the 37-key and 6-by-20 button contracts.
- Existing diagnostics, keyboard simulation, and audible-render tests remain
  hardware-independent.

| Command | Result |
| --- | --- |
| `pipenv verify` | PASS — lock is current |
| `pipenv run pytest -q` | PASS — 56 tests |
| `pipenv run ruff check .` | PASS |
| `pipenv run ruff format --check .` | PASS |
| `pipenv run mypy src tests` | PASS — 21 source files |
| `docker compose config --quiet` | PASS |
| `docker compose build` | PASS |
| Container `/api/health` | PASS — healthy service |

## Observed

A local Uvicorn server accepted HTTP and WebSocket connections. Headless Chrome
rendered the complete page at 1600 pixels wide, including the connection panel,
full-width stacked 37-key piano, bellows, enlarged 120-button left-hand surface,
explicit mapping controls, and raw event panel. The browser reported the
WebSocket as live. This was a software/browser observation with no FR-4X
connected.

The final Compose image ran on its loopback-only port 8765, selected because
another host service already owned port 8000. Its WebSocket reported the kernel
`Midi Through` port as one available input and output. A controlled loopback
sent note-on `[0x90, 60, 91]` and note-off `[0x80, 60, 0]`; both outbound events
returned as inbound WebSocket events with the expected note and velocity. The
ports were then explicitly disconnected. This observed the container's
software MIDI I/O path, not USB/FR-4X hardware or acoustic output.

## Pending

- Select the observed FR-4X ALSA input and verify raw events in the browser.
- Capture the H1 dataset and record the actual right-hand channel and leftmost
  note for each relevant instrument setup.
- Determine whether each left-hand physical button emits a single note, a
  cluster, controls, or mode-dependent combinations before replacing the
  provisional single-event learner.
- Exercise disconnect/reconnect with the physical FR-4X and record the result.
- Select a deliberate MIDI output and verify simulator output with a monitored
  synth or loopback before connecting performance equipment.
- Measure UI update latency separately from end-to-end accompaniment latency.

## Subjective

Visual resemblance and usability on the intended performance display remain
pending performer review. No musical-feel or stage-readiness claim is made.
