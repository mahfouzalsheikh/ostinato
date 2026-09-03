# KORG Style Import Support for Arranger Prototype

## Goal

Add support to the arranger application for using free KORG accompaniment styles as source material.

The application is a personal-use/open-source prototype. Downloaded KORG style files must **not be committed to the Git repository** unless their redistribution license explicitly allows it.

The implementation should:

- Provide instructions/scripts for obtaining free KORG styles.
- Store downloaded styles locally outside version control.
- Inspect KORG style packages.
- Convert/import usable style data into a vendor-neutral internal representation.
- Support arranger concepts including:
  - intros
  - endings
  - fills
  - break
  - variations
  - drums
  - percussion
  - bass
  - accompaniment tracks
  - tempo
  - time signature
  - chord-dependent note transformation
- Eventually allow styles to react in real time to chords played on the left-hand MIDI keyboard.

---

# Phase 1: Create Local Style Asset Structure

Create the following directories:

```text
assets/
  styles/
    korg/
      downloads/
      extracted/
      midi/
      converted/
      README.md

src/
  styles/
    models/
    importers/
      korg/
    playback/
```

Add these paths to `.gitignore`:

```gitignore
assets/styles/korg/downloads/**
assets/styles/korg/extracted/**
assets/styles/korg/midi/**
assets/styles/korg/converted/**
```

Keep the README tracked.

Do not commit downloaded KORG data files.

---

# Phase 2: Document Where to Download Free Styles

Create:

```text
assets/styles/korg/README.md
```

Document the following official sources.

## Primary source: KORG Arranger Bonusware

KORG provides a large collection of free arranger Bonusware here:

https://www.korg.com/us/features/arrangers/bonusware/

This should be the main source.

Useful initial packages include:

```text
Styl-v01.zip
Styl-v02.zip
Styl-v03.zip
Styl-v04.zip
Styl-v05.zip
Styl-v06.zip
Styl-v07.zip
Styl-v08.zip
Styl-v09.zip
Styl-v10.zip
Styl-v11.zip
Styl-v12.zip
PianoSty.zip
RealDrums.zip
TurkishArabicWorld.zip
```

The first 12 KORG volumes contain styles covering:

- Ballad
- Pop
- Rock
- Jazz
- Funk
- Latin
- World
- Ballroom
- Blues
- Country
- Movie

Download a representative subset first rather than everything.

Recommended initial test set:

```text
Styl-v01.zip
Styl-v08.zip
PianoSty.zip
RealDrums.zip
TurkishArabicWorld.zip
```

This provides enough musical variety to test the importer.

---

## Secondary source: KORG XE20 Bonus Styles

KORG also provides free XE20 style packages:

https://www.korg.com/caen/products/digitalpianos/xe20/bonus.php

Examples include:

```text
German.zip
PartyHit.zip
Korg_De.zip
Turk_1.zip
PianoSty.zip
Sound_Co.zip
Japanese.zip
```

Use these as additional test material.

---

# Phase 3: Create a Download Helper

Create:

```text
scripts/download_korg_styles.py
```

The script should NOT scrape random third-party websites.

Prefer one of these approaches:

1. Maintain a small manifest of approved official KORG URLs.
2. Let the developer manually download ZIP files into:

```text
assets/styles/korg/downloads/
```

Because KORG may change download URLs, the implementation should work even if downloading remains a manual step.

Create:

```text
assets/styles/korg/downloads/README.md
```

with instructions:

```text
1. Visit the official KORG Bonusware page.
2. Download desired ZIP packages.
3. Save them into assets/styles/korg/downloads/.
4. Run:

   python scripts/extract_korg_styles.py

5. Run:

   python scripts/inspect_korg_styles.py
```

---

# Phase 4: Extract Downloaded Packages

Create:

```text
scripts/extract_korg_styles.py
```

Requirements:

- Iterate through ZIP files in:

```text
assets/styles/korg/downloads/
```

- Extract each package into:

```text
assets/styles/korg/extracted/<package-name>/
```

- Preserve directory structure.
- Do not overwrite existing files unless `--force` is supplied.
- Produce a summary showing:
  - package
  - file count
  - extensions encountered
  - total size

Example:

```bash
python scripts/extract_korg_styles.py
```

Output example:

```text
Styl-v01
  .STY: 2
  .PCG: 1

PianoSty
  .STY: 3

RealDrums
  .STY: 2
  .PCM: 4
```

Do not assume actual counts match this example.

---

# Phase 5: Build a KORG File Inspector

Create:

```text
scripts/inspect_korg_styles.py
```

and reusable code under:

```text
src/styles/importers/korg/
```

For every discovered file collect:

```text
filename
extension
size
magic/header bytes
entropy
possible MIDI header offset
embedded ASCII strings
possible MIDI chunks
```

Specifically search each file for:

```text
MThd
MTrk
```

because these indicate Standard MIDI File structures.

Also inspect:

- RIFF headers
- ZIP signatures
- SysEx sequences beginning with `F0`
- textual markers
- style element names

Generate:

```text
assets/styles/korg/style_inventory.json
```

Example structure:

```json
{
  "packages": [
    {
      "name": "Styl-v01",
      "files": [
        {
          "path": "...",
          "extension": ".STY",
          "size": 12345,
          "midi_header_offsets": [],
          "strings": []
        }
      ]
    }
  ]
}
```

---

# Phase 6: Do NOT Assume .STY == MIDI

Some discussions online suggest certain KORG style files contain MIDI-like structures, but modern KORG `.STY` files can contain additional proprietary data.

Therefore:

DO NOT implement:

```python
rename(".STY", ".MID")
```

and assume that is sufficient.

Instead, determine the file generation/model and inspect its binary structure.

The importer must fail gracefully when the format is unknown.

Example:

```python
class UnsupportedKorgStyleFormat(Exception):
    pass
```

---

# Phase 7: Establish a MIDI-Based Interchange Format

The preferred intermediate representation should be Standard MIDI File data whenever possible.

KORG PA arrangers can export style material to MIDI, including complete styles separated by markers.

Design the importer around this format first.

Create:

```text
src/styles/importers/korg/midi_style_importer.py
```

Use an established Python MIDI library such as:

```text
mido
```

or an equivalent already present in the project.

Do not implement a complete MIDI parser manually unless necessary.

---

# Phase 8: Define a Vendor-Neutral Style Model

Create an internal model independent of KORG.

Suggested structure:

```python
Style
    id
    name
    source
    source_format
    tempo
    time_signature
    metadata
    elements
```

Where:

```python
StyleElement
    type
    name
    length_beats
    chord_variations
```

Element types should support:

```python
INTRO_1
INTRO_2
INTRO_3

VARIATION_1
VARIATION_2
VARIATION_3
VARIATION_4

FILL_1
FILL_2
FILL_3
FILL_4

BREAK

ENDING_1
ENDING_2
ENDING_3
```

Do not require every style to contain every element.

A chord variation should contain:

```python
ChordVariation
    source_chord
    tracks
```

Each accompaniment track:

```python
StyleTrack
    role
    midi_channel
    program
    bank_msb
    bank_lsb
    events
    chord_transform
```

Track roles:

```text
DRUM
PERCUSSION
BASS
ACC1
ACC2
ACC3
ACC4
ACC5
```

---

# Phase 9: MIDI Event Representation

Represent musical events independently of MIDI serialization.

For example:

```python
NoteEvent:
    start_tick
    duration_ticks
    note
    velocity

ControlChangeEvent:
    tick
    controller
    value

ProgramChangeEvent:
    tick
    program
```

A style track should contain ordered events.

Keep original MIDI metadata when practical.

---

# Phase 10: Parse KORG Style MIDI Markers

When importing a complete KORG-exported style MIDI file, inspect MIDI marker/meta events.

Identify element boundaries corresponding to sections such as:

```text
Intro
Variation
Fill
Break
Ending
```

Do not hard-code only one spelling.

Create a marker normalization layer.

Example:

```python
normalize_korg_marker(marker: str) -> StyleElementDescriptor
```

Log unknown markers rather than discarding them.

Example:

```text
Unknown KORG marker: "V1-CV2"
```

Store raw marker information in metadata.

---

# Phase 11: Support Chord Variations

KORG arranger styles may contain multiple chord variations for a style section.

Conceptually this may appear as identifiers such as:

```text
V1-CV1
V1-CV2
V2-CV1
...
```

Preserve these as distinct chord variations.

The internal model should NOT flatten all chord variations into a single MIDI loop.

Initially, record:

```text
element
CV number
original chord/key if detectable
tracks
events
```

If the original chord/key cannot yet be determined, retain the MIDI notes and metadata for future analysis.

---

# Phase 12: Build Chord-Relative Note Transformation

The arranger eventually needs to transpose accompaniment from the style's reference chord to the chord played by the performer.

Implement this separately from KORG import.

Create:

```text
src/styles/playback/chord_transform.py
```

API concept:

```python
transform_pattern(notes, source_chord, target_chord, track_role, rules)
```

Initially support:

```text
major
minor
dominant seventh
minor seventh
major seventh
diminished
augmented
sus2
sus4
```

Bass handling should preserve intended chord-root behavior where appropriate.

Drum and percussion tracks should normally not be transposed.

---

# Phase 13: Integrate With Existing Left-Hand Chord Detection

The arranger already has/should have left-hand MIDI chord detection.

Connect:

```text
MIDI input
    ↓
Chord detector
    ↓
Current chord
    ↓
Style engine
    ↓
Chord transformation
    ↓
Scheduled MIDI accompaniment
```

Do not couple chord detection directly to the KORG importer.

KORG importing should happen offline.

Playback should operate only on the internal `Style` model.

---

# Phase 14: Style Playback State Machine

Implement:

```text
STOPPED
INTRO
PLAYING_VARIATION
FILL
BREAK
ENDING
```

Transitions should support:

```text
start → intro → variation

variation → fill → new variation

variation → break → variation

variation → ending → stopped
```

Style element switching should happen musically, preferably on beat/bar boundaries rather than instantly.

---

# Phase 15: Instrument Mapping

KORG styles may refer to KORG-specific sounds.

Do not make correct playback depend upon having KORG sound banks.

Create a mapping layer:

```text
src/styles/instrument_mapping/
```

Fallback strategy:

```text
KORG program/bank
       ↓
General MIDI family
       ↓
available local sound
```

Examples:

```text
KORG bass sound → GM Acoustic Bass
KORG piano → GM Acoustic Grand
KORG strings → GM String Ensemble
KORG guitar → nearest GM guitar
```

Drum maps require special handling.

Preserve original:

```text
bank MSB
bank LSB
program number
```

in metadata so higher-quality mappings can be added later.

---

# Phase 16: Drum Mapping

Implement explicit drum mapping support.

Do not transpose drum note numbers with the chord.

Create:

```text
src/styles/instrument_mapping/drums.py
```

Initially map unknown KORG drum kits onto General MIDI percussion where possible.

Log unmapped notes.

Example:

```text
Unmapped percussion note:
  source kit: KORG Real Drums Kit X
  source note: 82
```

This will allow us to progressively improve drum compatibility.

---

# Phase 17: Create a Converted Style Format

Create a local normalized format.

Suggested layout:

```text
assets/styles/korg/converted/<style-id>/
    style.json
    patterns.mid
```

or optionally:

```text
style.json
events.msgpack
```

Prefer readability during the prototype stage.

Example `style.json`:

```json
{
  "version": 1,
  "id": "korg_ballad_001",
  "name": "Example Ballad",
  "source": {
    "manufacturer": "KORG",
    "package": "Styl-v01",
    "original_file": "USER01.STY"
  },
  "tempo": 78,
  "time_signature": [4, 4],
  "elements": {
    "variation_1": {},
    "variation_2": {},
    "fill_1": {},
    "intro_1": {},
    "ending_1": {}
  }
}
```

Do not design the format around KORG-specific binary structures.

---

# Phase 18: CLI Import Tool

Create:

```text
scripts/import_korg_style.py
```

Usage:

```bash
python scripts/import_korg_style.py <input>
```

Possible inputs:

```text
.STY
.MID
directory
.SET directory
```

Examples:

```bash
python scripts/import_korg_style.py \
  assets/styles/korg/midi/MyBallad.mid
```

Output:

```text
Detected:
  Format: KORG exported style MIDI
  Tempo: 84 BPM
  Meter: 4/4

Elements:
  Intro 1
  Variation 1
  Variation 2
  Variation 3
  Variation 4
  Fill 1
  Fill 2
  Break
  Ending 1

Tracks:
  Drums
  Percussion
  Bass
  ACC1
  ACC2
  ACC3
  ACC4
  ACC5

Converted successfully:
assets/styles/korg/converted/my-ballad/
```

---

# Phase 19: Style Inspection UI

Add a development UI screen for imported styles.

Display:

```text
Style name
Tempo
Time signature
Source
Available elements
Chord variations
Track list
Instrument mappings
Loop length
Event counts
Unsupported features
```

Provide controls:

```text
Play
Stop

Intro 1
Intro 2
Intro 3

Variation 1
Variation 2
Variation 3
Variation 4

Fill
Break

Ending
```

Also display the currently detected chord.

Example:

```text
Detected chord: Am7
Active style: Slow Ballad
Section: Variation 2
Next section: Fill 2
Measure: 12
```

---

# Phase 20: Development Fallback if Direct .STY Parsing Is Difficult

Do NOT block the project on reverse-engineering `.STY`.

Support this workflow first:

```text
KORG style
    ↓
KORG keyboard or conversion utility
    ↓
Standard MIDI File with markers
    ↓
our importer
    ↓
internal Style format
    ↓
arranger playback engine
```

KORG PA Manager currently advertises complete Style-to-MIDI export with markers.

It may therefore be useful during development even if it is not part of the final open-source application.

The application itself must not require PA Manager.

---

# Phase 21: Experimental Native .STY Parser

After MIDI importing works, investigate direct `.STY` loading.

Create:

```text
src/styles/importers/korg/native/
```

but consider it experimental.

Tasks:

- [ ] Collect `.STY` samples from several KORG generations.
- [ ] Record model/generation associated with each sample.
- [ ] Hex-dump files.
- [ ] Search for MIDI chunks.
- [ ] Search for marker text.
- [ ] Compare similar styles differing in only one property.
- [ ] Identify headers.
- [ ] Identify chunk lengths.
- [ ] Identify MIDI event blocks.
- [ ] Identify style-element tables.
- [ ] Identify program/bank mappings.
- [ ] Identify tempo.
- [ ] Identify time signature.
- [ ] Identify chord-variation metadata.
- [ ] Identify transposition metadata.
- [ ] Write format notes in:

```text
docs/korg-style-format.md
```

Native parsing must be isolated behind:

```python
KorgStyleImporter
```

so the rest of the arranger remains vendor-neutral.

---

# Phase 22: Tests

Create fixtures from locally available test data but do not commit copyrighted KORG style binaries.

Instead generate synthetic MIDI fixtures reproducing the relevant KORG marker structure.

Tests should cover:

- [ ] MIDI parsing
- [ ] marker recognition
- [ ] variation extraction
- [ ] intro extraction
- [ ] ending extraction
- [ ] fill extraction
- [ ] break extraction
- [ ] multiple chord variations
- [ ] track role detection
- [ ] program changes
- [ ] control changes
- [ ] tempo
- [ ] time signature
- [ ] loop boundaries
- [ ] chord transposition
- [ ] non-transposed drums
- [ ] bass transformation
- [ ] style-state transitions
- [ ] switching variations on bar boundaries
- [ ] unknown markers
- [ ] unsupported KORG binary formats

---

# Phase 23: Developer Diagnostics

Add verbose diagnostics:

```bash
python scripts/import_korg_style.py file.mid --debug
```

Include:

```text
MIDI format
ticks per beat
track count
marker list
SysEx events
channels used
note ranges
program changes
bank MSB/LSB
controllers
tempo changes
time signature changes
```

Provide:

```bash
--dump-events
--dump-markers
--dump-sysex
--dump-tracks
```

These will be especially important when reverse-engineering KORG exports.

---

# Phase 24: First Milestone

The first milestone is NOT native `.STY` support.

Milestone 1 is complete when:

- [ ] A KORG-originated style can be represented as MIDI.
- [ ] Our importer recognizes its sections.
- [ ] Variations can loop continuously.
- [ ] Drum, bass and accompaniment tracks play.
- [ ] Left-hand MIDI chords alter accompaniment harmony.
- [ ] Drums remain rhythmically unchanged.
- [ ] Variation changes occur on musical boundaries.
- [ ] Fill transitions work.
- [ ] Intro works.
- [ ] Ending works.
- [ ] The application UI displays style state.
- [ ] No proprietary style files are committed to Git.

At this point we will have a functioning KORG-derived accompaniment engine regardless of whether native `.STY` decoding is complete.

---

# Phase 25: Second Milestone

After Milestone 1:

- [ ] Implement direct native `.STY` inspection.
- [ ] Determine which KORG generations can be decoded reliably.
- [ ] Import supported `.STY` files directly.
- [ ] Add `.SET` directory scanning.
- [ ] Resolve referenced KORG sounds/drum kits.
- [ ] Improve chord-variation selection.
- [ ] Improve KORG-specific transposition behavior.
- [ ] Compare playback against the same style on an actual KORG arranger where possible.

---

# Architecture Rule

The final architecture should always remain:

```text
                    ┌─ KORG MIDI importer
                    │
KORG source ────────┼─ KORG STY importer
                    │
                    └─ future Yamaha/Roland/etc importers
                              │
                              ▼
                    Vendor-neutral Style
                              │
                ┌─────────────┴──────────────┐
                ▼                            ▼
          Chord Engine                 Style Scheduler
                │                            │
                └─────────────┬──────────────┘
                              ▼
                         MIDI Playback
                              │
                              ▼
                         Synth / MIDI Out
```

Do not allow the playback engine to depend directly on KORG file structures.

---

# Start Here

Codex should begin with these tasks, in this order:

- [ ] Create asset directory structure.
- [ ] Add downloaded KORG directories to `.gitignore`.
- [ ] Create `assets/styles/korg/README.md`.
- [ ] Implement ZIP extractor.
- [ ] Implement style-file inventory/inspection tool.
- [ ] Add MIDI parsing dependency if needed.
- [ ] Define vendor-neutral Style data model.
- [ ] Implement KORG-exported MIDI marker parser.
- [ ] Create CLI style inspector.
- [ ] Import one real KORG-originated style.
- [ ] Display its sections/tracks/events.
- [ ] Get Variation 1 looping.
- [ ] Add drums + bass + accompaniment playback.
- [ ] Connect left-hand chord detection.
- [ ] Implement chord-relative accompaniment.
- [ ] Implement variation switching.
- [ ] Implement fills.
- [ ] Implement intro/ending.
- [ ] Only then begin native `.STY` reverse engineering.

Do not spend significant time reverse-engineering proprietary `.STY` binary structures until the MIDI-based style playback pipeline is proven.
