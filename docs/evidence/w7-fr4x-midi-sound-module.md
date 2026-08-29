# W7 — FR-4X MIDI sound-module output

## Milestone boundary

W7 replaces the web arranger's host PCM destination with an explicit MIDI path
to the FR-4X internal Orchestra Bass, Orchestra Chord, and Drum parts. It keeps
the two W6 styles and transport controls. It does not add program/register
automation, a general style loader, or a hardware-validated input recognizer.

The standalone `ostinato keyboard --play` command remains a procedural PCM test
harness and is outside this web-output change.

## Documented

- Roland documents that USB COMPUTER carries MIDI rather than audio and that
  the FR-4X can respond as a sound module.
- The FR-4X MIDI implementation lists factory receive channels for Orchestra
  Bass, Orchestra Chord, and Drum as 5, 6, and 10. Ostinato presents these only
  as unconfirmed suggestions and blocks arranger playback until the user saves
  three distinct reviewed channels.
- Roland documents note positions 36, 38, and 42 in the drum maps. The two
  prototype styles use those positions for kick, snare, and closed hi-hat.
- External Seq. Playback defaults to Off. Enabling Bass & Chord external
  playback disconnects the physical left-hand keyboard from the corresponding
  internal parts; the setup UI discloses this before confirmation.

Sources: [FR-4X Reference Manual](https://static.roland.com/assets/media/pdf/FR-4x_reference_e01_W.pdf),
[FR-4X MIDI Implementation](https://static.roland.com/assets/media/pdf/FR-4x_MIDI_Implementation_e01_W.pdf),
and [FR-4X Tone List](https://static.roland.com/assets/media/pdf/FR-4x_Tone_List_e01_W.pdf).

## Automated

- A pure planner test verifies separate confirmed bass, chord, and drum
  channels, both meters, four-bar section orchestration, and documented drum
  note positions.
- A scheduler test verifies immediate dispatch through the MIDI service and
  owner-scoped note release on stop.
- FastAPI integration tests verify unconfirmed suggestions, distinct-channel
  validation, atomic persistence, safe handling of invalid saved routing,
  bounded part tests, live arranger MIDI dispatch, and note cleanup.
- All hardware-facing tests use an in-memory MIDI backend. They do not imply
  that a USB device, FR-4X sound generator, or analog output was exercised.

## Observed

- The rebuilt Compose service reported healthy and exposed the new web assets
  on loopback.
- The live container restored the exact observed FR-4X input/output port name
  and the saved treble 1, bass 2, and chord 3 input roles. These are observations
  of this connected instrument, not shared defaults.
- The live arranger status reported `output_mode: fr4x_midi` and
  `output_configured: false`; the API returned 5/6/10 only as unconfirmed
  suggestions. No setup test or arranger note was sent to the physical FR-4X.
- Headless Chrome rendered the compact arranger panel, Sound module setup
  action, locked Intro/Start buttons, and the confirmation message. This is a
  software/browser observation, not acoustic evidence.

## Pending human gate

- On the actual FR-4X, select its exact USB MIDI output in Ostinato.
- Review the configured O.Bass, O.Chord, and Drum receive channels rather than
  assuming factory values.
- Enable only the required External Seq. Playback groups, understanding the
  keyboard-disconnect behavior, and verify the three setup test buttons.
- Confirm that Start produces native drums and that a recognized left-hand
  chord produces native bass/chord accompaniment.
- Check stop, panic, ending completion, output disconnect, and service shutdown
  for stuck notes.
- Subjectively review registrations, velocity response, balance, voicing,
  rhythm, and the bass-stroke tempo rule. This is hardware/rehearsal evidence,
  not automated acceptance.

## Safety

The FR-4X analog output remains connected directly to the mixer. Ostinato sends
only accompaniment MIDI notes and never captures, processes, or relays that
analog signal. The web arranger sends no bank select, program change, System
Exclusive, volume, or pan messages, leaving native timbre selection on the
instrument.
