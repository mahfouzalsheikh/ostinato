# Local KORG style workspace

This directory is for user-supplied KORG arranger style material. Downloaded,
extracted, exported-MIDI, and converted files are local inputs or derivatives;
Git ignores them. Do not commit a style unless its redistribution license has
been checked and recorded separately.

## Official sources

- [KORG Arranger Bonusware](https://www.korg.com/us/features/arrangers/bonusware/)
  is the primary catalog.
- [KORG Pa80 Style to MIDI 1.06](https://www.korg.com/us/support/download/software/1/192/2455/)
  is KORG's legacy converter for individual Chord Variations. It is external
  freeware and is not distributed with Ostinato.
- [KORG XE20 bonus styles](https://www.korg.com/caen/products/digitalpianos/xe20/bonus.php)
  provide additional official material.

Start with a small, musically varied selection. The research brief recommends
`Styl-v01.zip`, `Styl-v08.zip`, `PianoSty.zip`, `RealDrums.zip`, and
`TurkishArabicWorld.zip`, but package names and availability can change. Verify
the source and terms on KORG's site at download time.

## Local workflow

1. Save official ZIP packages in `downloads/`.
2. Run `python scripts/extract_korg_styles.py`.
3. Run `python scripts/inspect_korg_styles.py`.
4. For a legacy style accepted by KORG's Pa80 utility, export each Chord
   Variation into one directory, preserving the utility's lowercase filenames
   such as `v1cv1.mid`, `i1cv1.mid`, `f1cv1.mid`, and `e1cv1.mid`.
5. Import that directory into readable vendor-neutral JSON:

   ```bash
   pipenv run python scripts/import_korg_style.py \
     assets/styles/korg/midi/example \
     --name "Example Style" \
     --source-file "USER01.STY#1" \
     --package "example.zip"
   ```

6. Render one fixed-source-pitch listening reference with an exact, locally
   configured General MIDI SoundFont:

   ```bash
   pipenv run python scripts/render_imported_style.py \
     assets/styles/korg/midi/example \
     --name "Example Style" \
     --soundfont /exact/path/to/configured.sf2 \
     --output assets/styles/korg/converted/example/variation-1-cv1.wav
   ```

The extractor rejects unsafe archive paths and does not replace existing files
unless `--force` is used. The binary inspector never treats `.STY` as MIDI just
because of its extension. Native `.STY` decoding remains experimental until a
specific KORG generation and its semantics have been established.

The inspector has catalog-only support for the strongly validated legacy
`KORF` directory variants observed across official packages. It lists primary
display names in physical converter order, but deliberately does not claim to
decode compressed musical bodies, sounds, chord rules, or section data.

The directory importer is a separate, strict path for Standard MIDI Files
exported in KORG's documented Pa80 convention. It accepts format-0, one-track
SMFs; maps one-based style channels 9–16 to Bass, Drum, Percussion, and
ACC1–ACC5; preserves integer ticks, notes, controllers, programs, banks, and
pitch bends; and keeps each Chord Variation distinct. The format alone cannot
authenticate file origin. Source-chord and KORG transposition semantics are not
present in these SMFs, so the listening renderer does not transpose notes and
uses General MIDI programs only as an explicit approximation.

The web service also discovers converted `*/style.json` documents from
`OSTINATO_KORG_STYLE_DIRECTORY` (this `converted/` directory by default).
Compose mounts it read-only and the arranger provides a library-group selector
before the filtered style selector. Live playback deliberately uses Variation
1 CV1 plus CV1 of
Intro 1, Fill 1/2, and Ending 1. Because the SMFs omit NTT/key settings,
Ostinato root-transposes melodic parts and adapts chord thirds/fifths/sevenths
using its documented local policy; it never transposes Drum or Percussion note
numbers. The source anchor is CV1's first Bass note, or the lowest melodic note
at the earliest CV1 onset when no Bass part is present. See
[`W40`](../../../docs/evidence/w40-korg-volume-2-library.md) for the current
policy and verification boundary.

Exact duplicates are defined over those five live sections, including track
roles, programs, banks, and events. Audit the local catalog with:

```bash
pipenv run python scripts/audit_korg_styles.py --fail-on-duplicates
```

## Directory purposes

- `downloads/`: untouched ZIP downloads from approved official sources
- `extracted/`: package contents produced by the extractor
- `midi/`: user-produced style MIDI exports, including per-style directories
- `converted/`: generated vendor-neutral JSON styles

Only this documentation and `downloads/README.md` are tracked.
