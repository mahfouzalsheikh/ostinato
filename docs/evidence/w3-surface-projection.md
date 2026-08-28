# W3 — Profile-driven surface projection

## Milestone boundary

W3 removes the separate browser mapping controls, aligns the 37-key piano from
the saved observed treble notes, projects detected bass/chord activity onto the
left button field, and suppresses the nonfunctional bellows display.

## Evidence

- **observed:** the saved local FR-4X profile reports treble channel 1 with
  sampled notes 62, 64, 65, 67, and 71. Treating sampled minimum 62 as the
  physical F-based keyboard origin caused the reported pitch shift.
- **automated:** the profile-derived surface code and static asset contract are
  covered by the complete hardware-free Python suite, lint, formatting, type
  checks, JavaScript syntax validation, and focused Node tests for F-aligned
  piano-window inference.
- **automated:** a headless Chrome inspection using the saved profile inferred
  piano base 53, placed MIDI C72 at visual index 19 (a C key), projected bass
  channel 2/note 48, projected chord channel 3/note 42, and found no bellows or
  explicit mapping panel.
- **untested:** no automated test sends events through the physical FR-4X; the
  user's report and saved profile are the hardware evidence for the diagnosed
  right-key offset.
- **pending:** confirm that physical C, E, and G illuminate visual C, E, and G
  across the desired octave after refreshing the rebuilt service.
- **pending:** confirm that bass-channel and chord-channel note activity lights
  the two distinct projected regions. Exact physical left-button position and
  chord semantics remain outside this milestone pending H1 recordings.

## Safety boundary

The piano uses the known F-to-F pitch-class geometry of the 37-key visual and
the MIDI note values observed from the configured instrument. Left-hand notes
are explicitly labeled as an activity projection; no FR-4X chord encoding,
bass layout, or physical button identity is invented. Analog accordion audio
remains on its direct mixer path.
