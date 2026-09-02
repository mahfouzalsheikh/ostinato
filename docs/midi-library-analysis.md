# Local MIDI library accompaniment analysis

## Scope and evidence boundary

W35 inspected the user-provided library at `~/projects/Mid` read-only. Python
suffix inspection found 5,063 MID, MIDI, or KAR files. Content hashing reduced
that to 4,453 unique files; 610 byte-identical copies were excluded before
aggregation so duplicated collections could not dominate the results.

The library does not contain one consistent license manifest. Ostinato does not
copy, bundle, publish, or play back any source file, named melody, identifiable
passage, or proprietary style format. Only corpus-level facts—meter, tempo,
instrument families, onset distributions, note lengths, velocity, chord
polyphony, and density around a likely lead stream—were used to guide new
Project Ostinato patterns.

Style labels are inferred from directory names, filenames, primary meter, and
General MIDI programs. They are useful arrangement evidence, not authoritative
musicological or copyright classifications. A likely lead stream was estimated
as the active non-drum stream with the highest mean register; other streams
were treated as accompaniment.

## Deduplicated corpora

| Corpus | Unique files | Primary meter | Median initial tempo | Typical accompaniment |
| --- | ---: | --- | ---: | --- |
| Tango | 83 | 2/4 | 100 BPM | piano, organ/reed, ensemble, guitar, bass |
| Accordion Waltz | 10 | 3/4 | 178 BPM | piano/organ, guitar, reed/brass, bass |
| Accordion Polka | 47 | 2/4 | 120 BPM | organ/accordion, piano, guitar, brass, bass |
| Brazilian | 31 | 4/4 | 104 BPM | guitar, flute/pipe, bass, piano, ensemble |
| Jazz | 79 | 4/4 | 122 BPM | piano, guitar/organ, bass, sparse ensemble |
| Country | 110 | 4/4 | 122 BPM | guitar, piano, bass, organ, ensemble |
| Latin | 39 | 4/4 | 120 BPM | piano, guitar, brass/reed, bass, percussion |
| Rock-and-roll | 26 | 4/4 | 144 BPM | guitar, piano, bass, reed/brass |
| Ballad | 11 | 4/4 | 120 BPM | piano/guitar, bass, ensemble, brass/organ |

Tempo ranges contain arrangement and metadata outliers, so medians informed
feel comparisons but did not replace Ostinato's established style defaults.

## Accompaniment findings

### Space around the lead

The estimated percentage of accompaniment attacks occurring away from a lead
attack was Tango 72%, Waltz 67%, Brazilian 82%, Jazz 66%, Country 69%, Latin
80%, and Ballad 69%. This supports short call-and-response figures rather than
a continuously doubled melody. Ostinato's normal melodic-answer lane is now a
monophonic chord-tone line; section solos remain independently shaped.

### Voicing

Two- and three-note attacks dominate every comping corpus. Tango recorded
5,739 simultaneous two-note and 2,455 three-note comp attacks; Polka recorded
12,254 and 14,411 respectively; Country recorded 24,672 and 21,155. Four-note
attacks occur as color, especially in Jazz and dominant harmony, rather than as
the only texture. Ostinato now cycles two-note shells, three-note close
voicings, selected open voicings, and occasional four-note dominant voicings.
All generated pitch classes remain inside the live recognized chord.

### Phrase development

Source accompaniment density is broadly balanced across four-bar windows, but
the actual onset grids vary continuously. The most useful corpus landmarks
were:

- Tango bass on beats 1 and 2 of each 2/4 cell, with comping also concentrated
  on the second eighth and final eighth/sixteenth; short note medians were 0.50
  beat for bass and 0.25 beat for comping.
- Waltz bass strongly favors beat 1, while chord and percussion weight beats 2
  and 3; bass notes sustain about one beat while chords remain shorter.
- Polka alternates bass on the two quarter-note beats with chords and snare on
  the two eighth-note upbeats, adding later pickups rather than repeating one
  bar literally.
- Brazilian bass favors beats 1 and 3 plus anticipations at 2-and and 4-and.
  Chords are distributed across downbeats and offbeats; kick concentrates on
  1, 2-and, 3, and 4-and while hats and auxiliary percussion remain layered.
- Jazz and blues bass centers on quarter notes but uses late-eighth and
  triplet-like approaches. Comping is much less square, with meaningful weight
  at 1-and, 2-and, 3-and, 4-and, and the final sixteenth.
- Country bass centers on beats 1 and 3 with secondary motion on 2, 4, and the
  upbeats. Snare strongly favors 2 and 4 while kick favors 1 and 3; guitar and
  piano attacks mix quarter notes with eighth-note anticipations.
- Latin comping and percussion have the flattest, most syncopated grid. Bass
  favors 1, 2-and, 3, 4, and 4-and, while percussion uses nearly every eighth
  position and selected sixteenths.

## Changes informed by the analysis

- Added changing shell, close, open, and dominant-color comp voicings across
  all fourteen built-in styles.
- Converted ordinary main-section answer gestures from chord stacks to sparse
  monophonic chord-tone phrases so they answer the accordion melody.
- Re-authored Country Two-Step, Reggae One Drop, Brazilian Samba, New Orleans
  Cha-Cha, and Blues Shuffle so bass, comping, kick, snare, percussion, and
  phrase pickups develop across the four measures instead of repeating one
  generated bar.
- Extended Samba chord gates and diversified its downbeat/anticipation balance
  to match the Brazilian aggregate more closely.
- Kept deterministic scheduling, current-chord safety, style-specific sampled
  instruments, and the direct FR-4X analog route unchanged.

## What was not inferred

No source file was assumed to document Roland channels, accordion chord
encodings, hardware timing, audio routing, or a redistributable style format.
The analysis does not establish ownership or redistribution permission for the
local library. Physical playability and musical realism remain a performer
listening decision.
