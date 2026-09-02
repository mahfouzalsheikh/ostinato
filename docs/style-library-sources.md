# Style library sources and licensing

Ostinato distributes six original built-in patterns and eight adapted human
grooves. This record identifies every external source used by the adapted pack,
its license, and the changes made. It is part of the attribution required when
redistributing the project.

## Open SFZ instruments for Classic Waltz

The Docker build downloads the following public assets and verifies the exact
archive checksum before extraction. License/readme files from each source stay
beside the samples in the image.

| Role | Asset | Version/source | License | Pinned identity |
| --- | --- | --- | --- | --- |
| Sampler | [sfizz](https://github.com/sfztools/sfizz) | 1.2.3 | BSD-2-Clause | commit `4e70dc0bef53b41f2853ed46e26f5911114c92d0` |
| Piano | [Salamander Grand Piano V3](https://sfzinstruments.github.io/pianos/salamander/) by Alexander Holm | 44.1 kHz, 16-bit distribution; 16 velocity layers plus release and resonance samples | CC BY 3.0 | SHA-256 `58750eb1366761e187f71ddb9b932355ea894d28ec4331e74ab8acb44c819936` |
| Pizzicato bass | [Meatbass](https://shop.karoryfer.com/pages/free-samples) | v1.001; four velocity layers and four round robins | CC0 | SHA-256 `bc053061d4f39fb76ba56bc1f323efa228d1f63757c331738812479bcf04fe96` |
| Brushed drums | [Swirly Drums](https://shop.karoryfer.com/pages/free-samples) | v1.104 | CC0 | SHA-256 `dbeb1ad04052da1bada490ced8cc7d9fdd3b21ea90f7c6020269968b70f836c3` |
| Acoustic/electric archtop guitar | [Shinyguitar](https://shop.karoryfer.com/pages/free-shinyguitar) | v1.002; 846 samples with separate microphone/pickup recordings, velocity layers, and round robins | CC0 | SHA-256 `23cf4030cbf9ce9e2c84d7cbb1c022fbca124bfff0ad118a14eda7cf6c921d7b` |
| Fingered/picked electric bass | [Black and Blue Basses](https://shop.karoryfer.com/pages/free-black-and-blue-basses) | v1.002; two five-string basses and more than 2,000 samples | CC0 | SHA-256 `cf77fc782abf996826fe75cfd948d356968de7c8b967c471c6a433835d2b4f55` |
| Live drum kit and percussion | [Virtuosity Drums](https://github.com/sfzinstruments/virtuosity_drums) | six-microphone contemporary kit plus General MIDI auxiliary percussion | CC0 | commit `9f04cf9a734527edfbb0a4eee1f674e45bbf71bc` |
| Flute, clarinet, trumpet, cello, violin | [Versilian Community Sample Orchestra 2 CE](https://github.com/sgossner/VSCO-2-CE) | selected sustain/vibrato and staccato SFZ mappings and only their referenced samples | CC0 | commit `6dd651d55dde97fd4028699be9d4481f26917891` |

The Salamander source requires attribution: **Salamander Grand Piano V3 by
Alexander Holm**, licensed under Creative Commons Attribution 3.0. Ostinato
does not modify its recordings; it mixes live-rendered notes from the supplied
SFZ mapping. Karoryfer's free libraries, Virtuosity Drums, and VSCO 2 CE
dedicate their included samples to CC0. No proprietary sampler content is
included.

`scripts/fetch-open-sfz-assets.sh` is the executable asset manifest. It fetches
only the selected VSCO mappings/sample directories rather than cloning the
complete orchestra into the final image.

Shinyguitar's supplied program expects its Aria bank file to define the sample
directory. The Docker build resolves that same relative directory explicitly
for direct sfizz loading and derives an acoustic preset by changing only the
documented microphone-blend controller default; the recordings are unchanged.

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

- The user-provided `~/projects/Mid` library was inspected read-only in W35.
  It has no single verified license manifest, so no MIDI, melody, passage,
  filename catalog, or style file is included. Only deduplicated corpus-level
  accompaniment statistics informed newly authored Ostinato rhythm and voicing
  changes; the method and evidence boundary are recorded in
  `docs/midi-library-analysis.md`.

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
