# W41 — KORG Arabic and World library expansion

Status: software and deployed-runtime gates complete; FR-4X, host-audio, and
performer listening gates pending.

## Scope

Expand the host-local KORG library with official KORG Bonusware, prioritizing
Arabic rhythms. Convert only structures accepted by KORG's Pa80 Style to MIDI
1.06 utility and Ostinato's strict importer, expose only styles supported by
the bounded live policy, and keep all proprietary sources and derivatives out
of the application image.

## Official packages and provenance

KORG's official [Arranger Bonusware catalog](https://www.korg.com/us/features/arrangers/bonusware/)
describes the packages and their advertised style counts.

- `TurkishArabicWorld.zip`: Turkish and Arabic sounds plus 30 styles. Download
  size: 7,833,290 bytes; SHA-256:
  `a06849efc81744bb2a408494716f750027144079b4e4812211c3bc6f576bcc1e`.
  Extracted `TA_WORLD.SET/STYLE/USER01.STY`: 513,797 bytes; SHA-256:
  `e904a68f1c9199e49c3ea89d9d4cc5bf20e8a6887313b8714f92b47fa23aade5`.
- `Styl-v04.zip`: eight World styles. Download size: 67,303 bytes; SHA-256:
  `c3451eba4627e33fa2da051055116bdef832bcba8473c6e01aec60dc3dbedf93`.
  Extracted style bank: 74,952 bytes; SHA-256:
  `df03be816d71e89baee60a51d4d3157694e3052fba864e900b820ecfe8849744`.
- `Styl-v08.zip`: 16 advertised World, Latin Ballad, and Ballroom styles.
  Download size: 116,486 bytes; SHA-256:
  `030b15fe6b5600c0bbb16facba7f3251a1e5e8f239e72546bbaf64d098a5246a`.
  Extracted style bank: 135,058 bytes; SHA-256:
  `210bf475b52450e158df7763ba470403e56d1842f25462635ae88023bc19325b`.

The official Pa80 converter ZIP SHA-256 is
`d5dae205afc9cdea4220b24964a11e4e14bbd3be77ac17ebce9df7e5708f08d2`;
its executable SHA-256 is
`0d0997432c6b722f62e6f7cf143bf185df912456e317cef772a7313db9dd9ef7`.
It ran under Wine in a disposable local container; no Windows host or KORG
hardware was used.

The Turkish/Arabic package also contains a KMP, two PCG files, and 24 PCM
files. Ostinato does not decode or distribute those proprietary sounds. Live
audio is explicitly a MuseScore General HQ General MIDI approximation.

## Accepted and rejected material

The live library gained 29 styles, increasing the KORG catalog from 16 to 45.

- Twenty-two accepted Turkish/Arabic/World styles: `Arap`, `Ayoub 1`,
  `Bonawara`, `Chegga`, `Cifteteli1`, `Cifteteli2`, `Daleona`, `Duble`,
  `Halay`, `Katakofti`, `Maksum`, `Malfuf`, `Masmodi1`, `Masmodi2`, `Misket`,
  `Morocco1`, `Saidi`, `Schubi`, `Sebari`, `Sek`, `Vahde`, and `Wachda`.
- Seven accepted Volume 4 World styles: `Armen Dance`, `Celtic Air`,
  `Old Celtic`, `Jig #2`, `Reel`, `HipHindiHop`, and `HindiPop4/4`.
- `Armen6/8Pop` converted consistently as 6/8 but was rejected because live
  imported styles currently require 2/4, 3/4, or 4/4.
- The Turkish/Arabic bank's `5/8`, `6/8`, `7/8`, `9/8`, and `TSM 9/8` entries
  were meter-preflighted but not added. `Samai 10/8` and `2/4` were also not
  added because the legacy converter declared them as 4/4, contradicting their
  names. The `3/4` entry was rejected because its exported live sections had
  inconsistent time signatures.
- Volume 8 was not added. Its first styles caused the official legacy utility
  to report corrupted event streams and internal assertions. No proprietary
  meaning or repair was guessed.

Every accepted style contains Variation 1 CV1 plus CV1 of Intro 1, Fill 1,
Fill 2, and Ending 1. KORG bank/program data is preserved in the vendor-neutral
documents, but GM programs are used for listening. Source-chord, NTT/key, and
higher-Chord-Variation semantics remain unavailable and are not claimed.

## Automated evidence

- Complete local suite: **201 passed**.
- Browser JavaScript checks, Ruff lint and formatting, and strict mypy: passed.
- All 45 imported documents passed strict library loading, five-section live
  validation, tonal-anchor validation, rhythm-span generation, and timeline
  generation.
- Focused KORG live/import/web tests: **36 passed**.

## Deployed-software evidence

- Rebuilt and recreated the Compose service from image manifest
  `sha256:b41b26420e1f28703e605bcbdc260a3d9110a327376bd893a5ea6adfff891770`.
- Compose health is **healthy** and `/api/health` returns `{"status":"ok"}` at
  `http://127.0.0.1:8765`.
- The deployed catalog reports exactly 45 imported KORG entries. All 29 new
  style-selector commands and timeline endpoints succeeded; transport was
  restored to stopped `modern_tango` with no arranger error afterward.
- Each of the 29 new styles rendered 48,000 stereo frames through the deployed
  MuseScore General HQ SoundFont. Every result was 192,000 bytes and
  non-silent. This check opened no ALSA or PipeWire output device.
- The converted library is mounted read-only at
  `/opt/ostinato-local-styles/korg`. A clean container from the image contained
  only `/app/assets/styles/korg/README.md`; downloaded ZIPs, extracted files,
  MIDI exports, candidate JSON, and converted JSON were absent.
- The disposable Wine converter containers, image, and build directory were
  removed after the host-local derivatives had been validated.

## Evidence boundary and human gate

- Official download provenance, checksums, secure extraction, legacy-converter
  behavior, MIDI export, JSON import, and software validation: **observed by
  software**.
- Original KORG sounds, authenticated NTT/key behavior, and higher Chord
  Variation meaning: **unavailable and not claimed**.
- FR-4X MIDI behavior: **untested** because no accordion hardware is available.
- Host ALSA/PipeWire accompaniment output: **untested in this milestone**.
- Musical balance, Arabic-rhythm fidelity under GM approximation, chord
  adaptation, transitions, and playability: **pending performer listening**.

The milestone stops at the listening gate. The deployed interface is ready for
the user to test all 45 KORG styles, including the 22 Arabic-focused additions.
