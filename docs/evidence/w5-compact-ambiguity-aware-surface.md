# W5 — Compact, ambiguity-aware live surface

## Milestone boundary

W5 reduces the sticky navigation and introductory hero so the live instrument
appears higher in the viewport. It also stops presenting an isolated bass MIDI
pitch as proof that the fundamental row was pressed.

## Evidence

- **documented:** Roland's FR-4X two-bass-row table assigns each pitch to both a
  fundamental button and a counterbass button in a different Stradella column:
  <https://static.roland.com/assets/media/pdf/FR-4x_reference_e01_W.pdf>.
- **automated:** JavaScript tests verify that E produces the fundamental-E and
  C-column counterbass-E candidates, and that recognized C-chord context
  resolves C to fundamental and E to counterbass.
- **automated:** headless Chrome against the rebuilt healthy Docker service
  measured the sticky header at 54 px. An isolated E bass highlighted `r2c13`
  and `r1c9` as candidates; adding a C-major chord removed both candidate
  states and produced exact active states at counterbass E `r1c9` and C-major
  `r3c9`.
- **pending:** physical FR-4X verification of candidate highlighting and
  chord-context resolution. No hardware exercise is implied by local tests.

## Display rule

An isolated bass pitch gives both possible buttons a reduced-intensity
candidate highlight. A recognized chord root resolves the common root bass to
the fundamental row and its major-third bass to the counterbass row. Other
bass pitches remain visibly ambiguous; Ostinato does not invent a physical
button identifier that is absent from the MIDI message.
