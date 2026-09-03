# W37 — real KORG Styl-v01 inspection

Status: real-package extraction and catalog software gate complete; musical
decode, playback, hardware, and performer gates pending.

## Scope

Inspect the user-downloaded official `Styl-v01.zip` with the W36 tools, record
what the bytes actually support, and add only the native parsing behavior that
can be strongly validated from this sample.

KORG's official [Arranger Bonusware catalog](https://www.korg.com/us/features/arrangers/bonusware/)
describes volume 1 as eight Ballad, Jazz, Latin, and Funk styles. The local ZIP
is retained outside version control under the project's KORG asset policy.

## Observed source

- Local archive: `assets/styles/korg/downloads/Styl-v01.zip`
- Archive size: 83,989 bytes
- Archive SHA-256:
  `03fec1a6e09424a6854e072d9f09dffe34e86f750cd4a1da9ba409aaef2ac822`
- ZIP contents: one file at `Styl-v01.set/STYLE/USER01.STY`
- Native bank size: 92,348 bytes
- Native bank SHA-256:
  `4c2a0ba362625c7a2cc18c207cf5d4e1046ab06288c4b9af44c1559cf6a8367f`
- Archived file timestamp: 2002-06-27 11:13 (timezone not encoded by ZIP)

The extracted bank has `KORF` at byte offset 23. It has no `MThd`, `MTrk`,
RIFF, or nested ZIP signature. Its entropy is 7.453012 bits per byte. Raw `F0`
bytes are reported only as possible byte offsets; without decoded event framing
they are not evidence of MIDI SysEx messages.

## Implemented behavior

The inspector now recognizes one catalog-only layout after validating all of
these observed invariants:

- `KORF` occurs at the observed fixed header offset;
- the directory has eight 24-byte records at the observed offset;
- every record has the same observed tag and its expected sequential slot;
- reserved bytes match the observed layout; and
- each 16-byte display-name field contains printable ASCII and padding.

If any invariant differs, the probe returns unknown. It does not try a looser
name scan or reinterpret arbitrary ASCII as a style directory.

The validated display names are:

1. SweetBallad
2. Blue Ballad
3. Unpl.Ballad
4. Be4 Swing
5. Latin Disco
6. Ba' Bayon
7. FashionFunk
8. Black Funk

The generated local inventory labels the format family
`korg_korf_style_bank`, the layout
`styl_v01_observed_eight_slot_directory`, the generation `unknown`, and support
level `catalog_only`.

## Automated and observed evidence

- The real archive extraction completed without overwrite or unsafe-path
  warnings: one `.STY`, 92,348 uncompressed bytes.
- The inventory processed the real file and returned exactly the eight display
  names above.
- Synthetic tests validate catalog acceptance and rejection after a directory
  invariant is corrupted; no KORG binary is used as a committed test fixture.
- Complete suite: `187 passed`; Ruff lint and formatting, strict mypy, and
  `git diff --check` passed.
- All 12 browser JavaScript tests passed.

## Evidence boundary and next gate

- Real package structure and checksums: **observed by software**.
- Eight style count and broad genres: **observed from KORG's official catalog**.
- Display names: **observed from the validated local bank directory**.
- KORG model/generation for this binary layout: **unknown**; the 2002 archive
  timestamp is not sufficient model evidence.
- Native musical-event, section, sound, and chord-transposition semantics:
  **unknown and unsupported**.
- Style playback and audio output: **untested**.
- FR-4X and KORG hardware: **untested**.
- Musical fidelity and performer playability: **pending**.

The next human gate is a Standard MIDI export of at least one Chord Variation
from this bank. KORG's official Pa80 Style to MIDI utility is one documented
conversion route, but it is a legacy Windows application and was not downloaded
or run in this Linux environment. A resulting `.mid` must be placed in
`assets/styles/korg/midi/` with the source style name and conversion tool/model
recorded. That file will allow section, track, event, and chord behavior to be
validated before arranger playback is connected.
