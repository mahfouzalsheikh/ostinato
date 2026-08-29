# W18 — Safe live-bass harmony

## Milestone boundary

Remove remaining off-chord accompaniment notes after the W17 register fix.
This milestone changes generated bass-note policy only. It does not change
recognized chord labels, FR-4X mappings, rhythm timing, or audio routing.

## Cause and correction

Every style contained a chromatic approach below the current chord root near
the end of its four-bar phrase. Because the real-time engine does not know the
next chord, that note could not be aimed at a confirmed target. For the
observed A7 chord in Modern Tango, it emitted A-flat while the A7 voicing's G
was still sounding and then overlapped the next A root.

Swing also treated a seventh as a generic color even when the recognized
major, minor, or diminished chord did not contain one. All blind approaches
are now chord-tone turnarounds. Swing uses a dominant seventh only for an
explicit dominant-seventh chord and an octave for the supported triads.

A second defect transposed the entire generated bass pattern from the most
recent live bass button. A live inversion now supplies only the first bass
attack of a bar; subsequent thirds, fifths, colors, and octaves remain relative
to the recognized chord root.

## Evidence

- **automated:** every generated pitched note across all six styles and all
  four supported chord qualities must belong to the recognized chord.
- **automated:** an A7/E inversion test verifies the generated swing line uses
  only A7 pitch classes instead of treating E as a new pattern root.
- **observed:** before correction, an in-memory trace found A-flat outside the
  live A7 chord in every style. Swing also produced unsupported sevenths for
  triads.
- **observed:** the post-correction trace found no pitch outside the recognized
  chord across all six styles and all four supported chord qualities.
- **pending:** acoustic confirmation with the actual accordion and selected
  Bluetooth/mixer path.

## Safety boundary

The accordion's direct analog voice remains unchanged. Ostinato still produces
accompaniment audio only, and no hardware mapping or device assumption was
added.
