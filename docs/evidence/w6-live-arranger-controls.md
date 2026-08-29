# W6 — Live arranger controls

## Milestone boundary

W6 exposes the existing procedural accompaniment as a backend-owned web
service, adds one contrasting original style, and connects saved left-hand MIDI
roles to tempo, harmony, and optional sync transport. It is a practical control
prototype around the partial P4 engine, not the future style-v1 MIDI
loader/planner/dispatcher.

## Automated

- Modern Tango is a four-beat style and Classic Waltz is a distinct three-beat
  render. Each transitions through a four-bar intro and four-bar ending.
- Bass tempo tests cover median timing, duplicate-stroke rejection, and a
  stable 120 BPM estimate.
- Chord tests cover normal note clusters and documented single-note D-Mode
  ranges.
- State-machine tests cover sync intro arming, start on saved-channel
  left-hand activity, stop after two silent bars, ending, panic, stopped-only
  style changes, and style default tempo.
- FastAPI tests cover the style catalog, stopped controls, saved channel
  propagation, and presence of the web arranger controls.

## Observed

- The rebuilt Docker service reported healthy with the saved bass channel 2 and
  chord channel 3 restored from the user's reviewed profile.
- The live API selected Classic Waltz at 96 BPM, returned to Modern Tango at
  120 BPM, and completed a silent-harmony Start/Stop smoke run without an
  `aplay` error. Acoustic output was not assessed.
- Headless Chrome rendered both styles and all five controls. Keyboard events
  toggled sync, armed the intro, started in the intro section, and stopped the
  backend transport; the browser and API agreed on sync state.

## Pending

- Physically confirm that representative bass strokes produce useful tempos.
- Physically verify normal/D-Mode chord recognition from labeled H1 fixtures.
- Confirm that two bars is the desired sync-stop grace period in rehearsal.
- Confirm acoustically that the container's accepted default ALSA stream reaches
  the intended accompaniment speakers at an appropriate level.
- Subjectively review both procedural styles, intros, endings, balance, and
  transition feel.
- Complete the tick-based style loader, planner, dispatcher, note lifecycle,
  FluidSynth path, latency suite, and endurance gates required by P4/P5.

## Safety

The FR-4X analog output remains on its direct mixer path. Ostinato opens only
the accompaniment PCM route, lazily on the first transport start. No automated
test claims that MIDI or audio hardware was exercised.
