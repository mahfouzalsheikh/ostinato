# W42 — KORG library groups and exact live deduplication

Status: software and deployed-runtime gates complete; FR-4X, host-audio, and
performer listening gates pending.

## Scope

Audit the host-local KORG catalog for duplicate playable styles, acquire the
complete primary style-package set from KORG's official Arranger Bonusware
catalog, import every style compatible with KORG's Pa80 Style to MIDI 1.06
utility and Ostinato's bounded live policy, and expose library groups before the
filtered style selector.

## Official package inventory and compatibility boundary

The official [KORG Arranger Bonusware catalog](https://www.korg.com/us/features/arrangers/bonusware/)
was the source of 46 primary ZIP packages: all 42 style-volume rows, Piano
Styles, Real Drums, Turkish Arabic World, and Mexican Styles. Optimized copies,
model preload bundles, hardware-card-only material, pads, sounds, and
third-party rows were not counted as additional primary style libraries.

- All 46 ZIPs downloaded without a partial file and were securely extracted.
- The extraction inventory contains 148 files and 64 `.STY` banks.
- Every bank variant was opened in a disposable Wine container and its first
  live Variation 1 CV1 was exported through KORG's own legacy utility.
- Eleven banks produced a valid Standard MIDI File: Volumes 1–7, both Piano
  Styles banks, Real Drums, and Turkish Arabic World. Together they advertise
  126 source style slots.
- The other 53 banks, including all tested Pa700/Pa1000/Pa4X variants and the
  superficially legacy-looking Volumes 8–23, failed the real musical-data
  export gate. A readable directory header was never treated as proof that the
  compressed style body was compatible.

The accepted banks were exported as Variation 1 CV1, Intro 1 CV1, Fill 1 CV1,
Fill 2 CV1, and Ending 1 CV1. The strict importer then checked SMF structure,
channel roles, integer timing, a supported 2/4–4/4 meter, a melodic tonal
anchor, rhythm spans, and timeline generation.

Twenty-one of the 126 advertised slots are not in the final live library:

- nine Turkish Arabic World aliases had byte-for-byte identical five-section
  live payloads and were recoverably quarantined;
- eight Turkish Arabic World entries failed the existing meter or inconsistent
  export gates;
- `Armen6/8Pop`, Volume 5's `6/8 Ballad`, and Real Drums' `Slow 6/8` are outside
  the current live meter policy; and
- Volume 3's `Jazz-4-tett` did not produce a complete five-section export.

## Duplicate audit

The new fingerprint includes every selected section's musical length, track
role, MIDI channel, program and bank, and ordered controller, program, pitch,
and note events. The original 45-entry library contained one ten-item exact
group: `Bonawara`, `Chegga`, `Daleona`, `Katakofti`, `Masmodi1`, `Masmodi2`,
`Morocco1`, `Saidi`, `Schubi`, and `Wachda`. A fresh direct export of `Saidi`
confirmed that this was the converter-visible CV1 payload, not a batch naming
mistake. `Saidi`, the earliest source-bank slot in the group, remains canonical;
the nine aliases were moved to `assets/styles/korg/duplicates/w42-exact-live/`.

The final 105-style catalog has zero duplicate display names and zero duplicate
five-section live fingerprints. `scripts/audit_korg_styles.py
--fail-on-duplicates` makes this gate repeatable.

## Grouped interface

The arranger catalog now exposes a stable `group` for every style. The browser
first offers a **Style group** selector, then alphabetically filters the existing
**Style** selector within that group. The selected backend style remains stable
while the user browses another group, including across periodic status polls.
The selectors are disabled together during playback.

The KORG groups and live counts are:

- Volume 1: 8; Volume 2: 8; Volume 3: 7; Volume 4: 7;
- Volume 5: 7; Volume 6: 8; Volume 7: 6;
- Piano Styles: 26; Real Drums: 15; and Turkish Arabic World: 13.

Group-qualified stable IDs prevent equal display names in separate libraries
from colliding. Existing IDs remain unchanged.

## Automated evidence

- Complete local suite: **209 passed**.
- Duplicate audit: **105 styles; 0 duplicate groups**.
- Browser group-selector tests, Ruff formatting/lint, and strict mypy: passed.
- Native catalog, strict importer, stable group ID, and arranger catalog tests:
  passed.

## Deployed-software evidence

- Rebuilt and recreated the Compose service from image manifest
  `sha256:a328e42c2590a5e01e7c2f88e9ee0e8ab0d09fe10a20c3f038aedc9942b3519d`.
- Compose health is **healthy** and `/api/health` returns `{"status":"ok"}` at
  `http://127.0.0.1:8765`.
- The deployed catalog reports 119 total styles: 14 built-ins and exactly 105
  imported KORG styles in the ten expected groups.
- All 105 deployed KORG style-selection commands and timeline endpoints
  succeeded. Transport was restored to stopped `modern_tango` with no arranger
  error afterward.
- Every imported style rendered 48,000 stereo frames through the deployed
  MuseScore General HQ SoundFont. Each result was 192,000 bytes and non-silent.
  This check opened no ALSA or PipeWire output device.
- The disposable Wine converter containers and image were removed, and its
  temporary build and probe directories were moved to desktop trash. Official
  ZIPs, extracted sources, MIDI derivatives, and converted JSON remain only in
  the ignored host-local workspace.

## Evidence boundary and human gate

- Official download, secure extraction, catalog inspection, KORG utility
  behavior, MIDI export, strict import, duplicate fingerprinting, and local
  software checks: **observed by software**.
- Original KORG sounds, authenticated NTT/key behavior, and higher Chord
  Variation meaning: **unavailable and not claimed**. Playback uses the
  MuseScore General HQ General MIDI approximation.
- FR-4X MIDI behavior: **untested** because no accordion hardware is available.
- Host ALSA/PipeWire accompaniment output: **untested in this milestone**.
- Musical balance, timing, transitions, and playability: **pending performer
  listening**.

The milestone stops at the listening gate after deployment. The grouped
interface is intended for user testing, not a claim of performer acceptance.
