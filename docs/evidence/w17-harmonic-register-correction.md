# W17 — Harmonic register correction

## Milestone boundary

Correct the off-key pitched layer reported after the W16 style overhaul. This
milestone changes harmonic note construction and regression coverage only. It
does not change FR-4X mappings, detected chords, audio routing, or style rhythm.

## Cause and correction

The sampled reed/brass voice and procedural string fallback used MIDI note 67
(G) as a register base, then added the recognized chord root. A register base
must preserve pitch class C and differ only by octaves. The defect therefore
shifted those notes by a perfect fifth: for an A-flat major chord, the sampled
reed emitted E-flat, G, and B-flat.

All pitched bases are now named C anchors at MIDI 36, 48, 60, or 72. The
sampled reed/brass and procedural upper strings use MIDI 72. The same A-flat
major trace now emits A-flat, C, and E-flat in bass, comp, and reed roles.

## Evidence

- **automated:** a table-driven test renders every built-in style with major,
  minor, dominant-seventh, and diminished A-flat chords and verifies every
  comp, reed, and pad note belongs to the recognized chord pitch-class set.
- **automated:** a separate procedural-renderer test verifies its upper string
  frequencies are constructed from the recognized chord pitch classes.
- **observed:** an in-memory Alpine Polka trace changed the reed/brass output
  from E-flat–G–B-flat to A-flat–C–E-flat for recognized A-flat major.
- **pending:** acoustic confirmation through the selected Bluetooth/mixer path.

## Safety boundary

The fix changes accompaniment pitches only. The accordion's analog voice
remains on its direct mixer path, and no hardware channel or device assumption
was added.
