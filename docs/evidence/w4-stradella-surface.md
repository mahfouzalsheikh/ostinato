# W4 — Two-bass-row Stradella surface

## Milestone boundary

W4 replaces the generic left-hand activity projection with the documented
FR-4X **2 Bass Rows** Stradella geometry. It maps bass pitch activity to the
fundamental/counterbass region and groups chord-channel note clusters into one
major, minor, dominant-seventh, or diminished button.

## Evidence

- **documented:** Roland's FR-4X reference manual identifies Bass & Chord mode
  as Stradella, defines the standard mode as two bass rows plus four chord rows,
  and provides the exact 20-column button table:
  <https://static.roland.com/assets/media/pdf/FR-4x_reference_e01_W.pdf>.
- **documented:** the same manual states that normal chord transmission sends
  all chord note numbers and documents single-note D-Mode ranges for major,
  minor, seventh, and diminished chords.
- **automated:** focused JavaScript tests cover the official C-column geometry,
  normal chord-note classification, and D-Mode decoding.
- **automated:** headless Chrome with the saved profile placed C bass at `r2c9`
  and a C-major note cluster at `r3c9`; with C major held, E bass moved to the
  counterbass button `r1c9`, matching the documented C column.
- **pending:** physical verification that C bass and C major/minor/seventh/
  diminished presses illuminate the corresponding central Stradella column.
- **pending:** confirm whether the user's FR-4X B&C Mode is **2 Bs Rows**. The
  alternative three-bass-row Stradella variants have different geometry and
  are not selected implicitly.

## MIDI ambiguity

The official table assigns the same MIDI pitch to a fundamental button and to
a counterbass button in another column. A standalone bass note therefore does
not uniquely identify which physical switch was used. Ostinato uses an active
recognized chord root as context for the common counterbass-major-third case
and otherwise displays the fundamental. This limitation is explicit and does
not invent a proprietary button identifier.
