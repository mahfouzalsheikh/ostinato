# Style library sources and licensing

Ostinato distributes six original built-in patterns and eight adapted human
grooves. This record identifies every external source used by the adapted pack,
its license, and the changes made. It is part of the attribution required when
redistributing the project.

## Groove MIDI Dataset pack

The drum feel references come from the **Groove MIDI Dataset** by Jon Gillick,
Adam Roberts, Jesse Engel, Douglas Eck, and David Bamman, published by Google
LLC. The dataset is licensed under
[Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)
and is available from the
[official dataset page](https://magenta.withgoogle.com/datasets/groove).

Ostinato does not distribute the source MIDI files or recordings. The selected
performances were reduced to short four-bar onset and relative-dynamic models;
microtiming was quantized, drum voices were mapped to the available General MIDI
palette, fills were simplified, and every bass, chord, pad, and melodic phrase
was newly authored to follow live accordion harmony. The adaptations are:

| Ostinato style | GMD performance reference |
| --- | --- |
| Motown Soul | `drummer7/session2/106_soul-motown_104_beat_4-4.mid` |
| Funk Pocket | `drummer1`, `drummer5`, `drummer7`, and `drummer8` `eval_session/1_funk-groove1_138_beat_4-4.mid` |
| Soft Pop Ballad | `drummer7/session3/11_pop-soft_83_beat_4-4.mid` |
| Country Two-Step | `drummer1/session2/10_country_114_beat_4-4.mid` |
| Reggae One Drop | `drummer5/session2/5_reggae_126_beat_4-4.mid` |
| Brazilian Samba | `drummer5/session2/17_latin-brazilian-samba_110_beat_4-4.mid` |
| New Orleans Cha-Cha | `drummer5/session2/8_neworleans-chacha_124_beat_4-4.mid` |
| Blues Shuffle | `drummer4/session1/6_blues-shuffle_134_beat_4-4.mid` |

## Libraries evaluated but not bundled

- [MMA — Musical MIDI Accompaniment](https://mellowood.ca/mma/downloads.html)
  publishes more than 1,000 patterns, but the supplied files are GPL-2.0. They
  were not copied into this MIT-licensed repository.
- [JJazzLab](https://www.jjazzlab.org/en/resources/) supports Yamaha style files
  and offers a large community archive. The archive does not state sufficiently
  clear per-file redistribution rights for bundling here, so no community or
  Yamaha style file was copied.
- Yamaha's official
  [MIDI Song to Style manual](https://usa.yamaha.com/files/download/other_assets/4/2179884/MIDI_Song_to_Style_owners_manual_En_B0.pdf)
  documents the professional arranger vocabulary of Rhythm 1–2, Bass, Chord
  1–2, Pad, Phrase 1–2, and Intro/Main/Fill/Break/Ending sections. Ostinato uses
  that vocabulary as an architecture benchmark only; it contains no Yamaha
  musical data or proprietary style-file parser.
