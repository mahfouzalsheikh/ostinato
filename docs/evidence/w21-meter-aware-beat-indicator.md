# W21 meter-aware beat indicator evidence

Status: automated software evidence and deployed browser observation complete;
audible hardware-alignment confirmation pending.

## Scope

The arranger now exposes its rendered musical position as integer ticks. The
web surface anchors a local animation to each backend status sample and advances
one numbered light per quarter-note beat. The light count comes from the style
meter: two for Alpine Polka, three for Classic Waltz, and four for the 4/4
styles. Beat one uses a distinct amber downbeat treatment.

The browser clock does not own transport state. It only interpolates from the
latest backend tick, tempo, and meter and is re-anchored by the existing 350 ms
status refresh. Stopping the arranger clears the active light.

## Verification

- Python unit tests cover integer renderer ticks, meter wrapping, and stopped
  state.
- JavaScript unit tests cover 2/4, 3/4, 4/4, tempo projection, and stopped
  behavior.
- Full local software suite: passed (`131 passed`, formatting and type checks
  passed); all 12 browser-module tests passed.
- Container rebuild/restart: passed; the container and API report healthy.
- Deployed browser observation: passed. A silent running transport reported
  position tick 207 and zero-based beat index 2 while the page highlighted
  numbered light 3 of 4. The transport was stopped immediately afterward.
- Audible alignment with FR-4X performance: pending user confirmation.
