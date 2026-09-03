# W39 — Live KORG style library and interface integration

Status: software and deployed-runtime gates complete; FR-4X, host-audio, and
performer listening gates pending.

## Scope

Expose the eight locally imported `Styl-v01` styles in the existing arranger
interface and make their exported MIDI material usable by the live backend.
Keep all KORG source and generated derivative files host-local, and do not
claim unavailable KORG NTT/key or original-patch semantics.

## Implemented behavior

- A read-only local library validates version-1 style JSON and discovers only
  direct `*/style.json` documents beneath the configured library directory.
- Compose bind-mounts `assets/styles/korg/converted` read-only at runtime. The
  directory contents remain excluded from both Git and the Docker build
  context; only an empty tracked placeholder keeps the mount point available
  in a fresh checkout.
- All eight styles appear in the existing selector with a `KORG` label,
  description, provenance, default tempo, and source meter. Be4 Swing is
  exposed as 2/4; the other seven are 4/4.
- The arrangement timeline endpoint and browser visualization show the exact
  Variation 1 CV1 notes grouped as Bass, ACC1–2, ACC3, ACC4–5, and
  Drum/Percussion lanes.
- Live playback uses Variation 1 CV1 for Main, and CV1 of Intro 1, Fill 1,
  Fill 2, and Ending 1 for the corresponding controls. Pattern and section
  lengths come from integer source ticks. Main loops continuously, fills and
  endings start at the next bar, and an intro transitions to Main at its exact
  source length.
- Program changes use bank-0 General MIDI approximations for melodic roles.
  Both percussion roles always use the GM percussion kit at bank 128/program
  0, including later source program changes. Controller and signed pitch-wheel
  events are scheduled at their source ticks.
- Tempo changes preserve the musical beat epoch. Chord changes clear scheduled
  melodic events and currently sounding melodic voices without transposing or
  cutting drum/percussion voices.

## Explicit chord policy

KORG's official SMF export description includes time signature, bank/program,
and expression data but does not include the Style Record NTT/key parameters.
Live playback therefore uses an explicitly Ostinato-defined policy, not a
claim about KORG hardware behavior:

1. Use the earliest Variation 1 CV1 Bass note as the source tonal anchor. The
   observed anchor is C in all eight imported styles.
2. Root-transpose every melodic role to the detected chord root using the
   nearest signed pitch-class displacement.
3. Adapt source third-family intervals (minor/major third), fifth-family
   intervals (diminished/perfect fifth), and seventh-family intervals to
   Ostinato's four detected chord qualities. Other intervals retain their
   root-relative color.
4. Preserve every Drum and Percussion note number exactly.

Only CV1 is selected because the exports do not authenticate the musical
meaning of higher Chord Variation numbers. This boundary is surfaced in the
UI as “CV1 · GM program approximation · Ostinato chord adaptation.”

## Automated evidence

- Complete required local suite: **200 passed**.
- Browser asset/API regression checks, Ruff lint and formatting, and strict
  mypy: passed.
- Deterministic tests cover strict JSON loading, malformed documents, catalog
  selection, the timeline API, exact pattern looping, intro/Main transition,
  both Fill controls, Ending completion, chord-tone adaptation, unchanged
  percussion pitches, and GM percussion program normalization.
- A hardware-free pass drove Intro, both Fills, Ending, and a non-C dominant
  chord through all eight real imported documents with fake synth timing.
- Docker regression checks confirm the proprietary inputs/derivatives remain
  excluded from the image and that the runtime library mount is declared
  read-only.

## Deployed-software evidence

- Rebuilt and recreated the Compose service from image manifest
  `sha256:d4a4313620457e6f7889e6073e4ca21263a45b40f12d168893a90747b290c40d`.
- Compose health: **healthy**; `/api/health` returned `{"status":"ok"}` at
  `http://127.0.0.1:8765`.
- The live status API returned exactly eight imported catalog entries, and all
  eight selector commands and timeline endpoints succeeded. The transport was
  restored to stopped Modern Tango afterward.
- Docker inspection reported the local KORG library as a bind mount with
  `RW=false`.
- Inside the deployed container, every imported style rendered 48,000 stereo
  frames through the configured MuseScore General HQ SoundFont. All eight PCM
  buffers were the expected 192,000 bytes and contained non-zero audio data.
- The deployed real-synth probe exposed and then verified the fix for Latin
  Disco's later percussion program change; the final pass completed for all
  eight styles without a FluidSynth error.
- The deployed renderer also exercised each source Intro 1 CV1 through its
  exact transition to Main. No ALSA/PipeWire device or physical hardware was
  opened for this verification.

## Evidence boundary and human gate

- Catalog, selection, timeline, scheduling, and non-silent FluidSynth PCM:
  **observed by deployed software**.
- Proprietary KORG sources absent from the image and read-only at runtime:
  **observed by deployed software**.
- Original KORG sounds, NTT/key behavior, and higher-CV meaning: **unavailable
  and not claimed**.
- FR-4X MIDI behavior: **untested** because no accordion hardware is available.
- Host ALSA/PipeWire accompaniment output: **untested in this milestone**; the
  deployed synth check deliberately did not open an audio device.
- Musical balance, chord adaptation quality, transitions, and playability:
  **pending performer listening**.

The milestone stops at the listening gate. The deployed interface is ready for
the user to select the KORG entries and judge their musical behavior through
the already configured accompaniment output.
