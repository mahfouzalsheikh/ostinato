# W11 — Right-hand upper-G extension

## Milestone boundary

Extend the existing profile-driven right-hand piano projection from F–F to
F–G. This adds the two performer-reported missing positions, F-sharp and G,
without changing the saved treble channel or shifting the established pitch
alignment.

## Evidence

- **observed:** the performer reports that the local accordion's right-hand
  keyboard continues through G rather than ending at F.
- **automated:** the visual constant is 39 positions; an F-aligned MIDI base of
  53 ends at MIDI 91, whose pitch class is G.
- **automated:** the setup-window test keeps the existing sampled profile
  centered at base 53, so previously corrected C, E, and G positions do not
  shift.
- **untested:** no automated test presses the two physical upper keys.
- **pending:** confirm that physical upper F-sharp and G illuminate the final
  two visual keys after refreshing the rebuilt service.

## Safety boundary

The extra positions follow the performer's hardware observation; they are not
claimed as a general FR-4X factory mapping. MIDI notes remain derived from the
saved observed treble channel and inferred base. Accordion analog audio remains
on its direct mixer path.
