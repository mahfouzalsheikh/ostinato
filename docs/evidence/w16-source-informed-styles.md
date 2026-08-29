# W16 — Source-informed style vocabulary and Classic Tango

## Milestone boundary

Improve the musical construction of the six built-in accompaniment styles and
add Classic Tango. This milestone changes original rhythmic vocabulary,
orchestration roles, articulation, and catalog metadata. It does not import or
copy a commercial arranger style, change FR-4X mappings, or route the
accordion's analog voice through Ostinato.

## Research translated into implementation

- The Universidad Nacional de La Plata describes tango accompaniment as a
  vocabulary including marcato in four and two, sincopa, arrastre, 3-3-2,
  contrapuntal lines, and final cadences. A related UNLP paper distinguishes
  3-3-2 as a later vanguard practice. Classic Tango therefore uses marcato and
  sincopa without a generic drum kit, while Modern Tango retains its 3-3-2
  identity.
- A University of Sao Paulo music-computing study extracted multiple bossa
  guitar patterns from Joao Gilberto performances and emphasizes expressive
  variations rather than one exact repeated template. Midwest Clinic rhythm
  section material specifies bass and bass drum on beats one and three,
  root/fifth bass motion, straight-eighth timekeeping, cross-stick, and
  independent two-bar comping. The bossa style now separates those roles.
- Baylor's open piano text identifies waltz bass as downbeat bass followed by
  two upper chord attacks. The waltz keeps that invariant while varying
  inversion, dynamics, and sparse orchestral responses.
- Yamaha's walking-bass material describes one note per beat, chord-tone
  outlining, and chromatic approach notes. Swing bass roles resolve from the
  live chord quality. Blind chromatic approaches are intentionally deferred
  until the engine knows the following chord target.
- Texas Christian University program research describes polka's signature
  oom-pah accompaniment and high-energy coda. Polka now preserves strict bass
  downbeats and chord upbeats, reserving denser motion for its fourth-bar turn.

## Sources

- [UNLP tango arranging curriculum](https://www2.fba.unlp.edu.ar/extension/arreglos-para-conjuntos-de-guitarras-en-el-tango/)
- [Rinaldi and Ordas, tango rhythmic schemes and percussion (UNLP PDF)](https://sedici.unlp.edu.ar/bitstream/handle/10915/74072/Documento_completo.pdf-PDFA.pdf?isAllowed=y&sequence=1)
- [Extracting Patterns from Guitar Accompaniment Data (University of Sao Paulo PDF)](https://compmus.ime.usp.br/sbcm/2005/papers/sbcm-paper-2005-4.pdf)
- [Suggested Rhythm Section Patterns for Common Styles (Midwest Clinic PDF)](https://www.midwestclinic.org/user_files_1/pdfs/clinicianmaterials/2005/victor_lopez.pdf)
- [Waltz bass accompaniment (Baylor Piano Basics)](https://openbooks.library.baylor.edu/pianobasics/chapter/accompaniment-styles-broken-chord-alberti-bass-and-waltz-bass/)
- [How to Construct Walking Basslines (Yamaha)](https://hub.yamaha.com/guitars/bass/how-to-construct-walking-basslines/)
- [Polka in C program note (Texas Christian University PDF)](https://finearts.tcu.edu/music/files/_programs/HarpEnsemble-Recital_042026.pdf)

## Evidence

- **automated:** the catalog exposes six distinct styles, including Classic
  Tango, with four valid groove bars and four-bar intro/ending contracts.
- **automated:** tests assert Classic Tango's marcato-in-four,
  marcato-in-two, sincopa, and drumless sampled orchestration; bossa role
  separation; quality-aware swing bass; and polka oom-pah placement.
- **automated:** sampled rendering uses independent bass, comp, reed, pad, and
  timekeeper onsets, per-hit accents, and style-specific note durations.
- **observed:** an in-container native FluidSynth render exercised all four
  supported chord qualities over every main phrase plus dominant-seventh intro
  and ending passages. Style peaks measured 24,434–29,149 and main-phrase RMS
  measured 2,518–4,569 on signed 16-bit PCM, with zero clipped samples and no
  native rendering errors.
- **pending:** performer assessment of groove authenticity, voicing, balance,
  intros, endings, and useful tempo range through the selected mixer/speakers.

## Safety and provenance

All patterns are original implementations of general rhythmic principles from
the cited educational and academic sources. No proprietary MIDI/style file or
copyrighted transcription was imported. Ostinato generates accompaniment
audio only; the FR-4X analog signal remains on its direct mixer path.
