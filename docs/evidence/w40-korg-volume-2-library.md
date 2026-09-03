# W40 — KORG Styles Volume 2 library expansion

Status: software and deployed-runtime gates complete; FR-4X, host-audio, and
performer listening gates pending.

## Scope

Download KORG's official `Styl-v02.zip`, convert its eight legacy Pa-series
styles with KORG's Pa80 Style to MIDI 1.06 utility, add the live sections to
the host-local imported-style library, and expose them through the deployed
arranger interface. This expands the local KORG catalog from eight to sixteen
styles without bundling proprietary inputs or derivatives in the image.

## Source and conversion evidence

- Official package URL:
  `https://www.korg.com/download/global/paseries/bonusware/Styl-v02.zip`
- Download: 50,005 bytes; SHA-256
  `f3958300d78fd76fb7aab3d72230b40055acca9a713d48112f85b9889df7e819`.
- Extracted `Styl-v02.set/STYLE/USER01.STY`: 56,649 bytes; SHA-256
  `9bb37988a03a147a173ac0ff99ac34151dde0154c97cb76522d798b5f9b23036`.
- Official Pa80 converter ZIP SHA-256:
  `d5dae205afc9cdea4220b24964a11e4e14bbd3be77ac17ebce9df7e5708f08d2`.
  Converter executable SHA-256:
  `0d0997432c6b722f62e6f7cf143bf185df912456e317cef772a7313db9dd9ef7`.
- The Windows converter ran under Wine in a disposable container. The
  container and its temporary image were removed after the MIDI exports were
  persisted in the ignored host-local workspace.
- The converter displayed and exported these eight bank slots:
  `8BtStrumRok`, `8 Bt GtrBld`, `8 Beat Pop`, `Heavy 8Beat`,
  `16BtStrmRok`, `16Bt GtrBld`, `16 Beat Pop`, and `Heavy16Beat`.

The imported documents contain Variation 1 CV1 plus CV1 of Intro 1, Fill 1,
Fill 2, and Ending 1, which are the complete set of sections consumed by the
bounded live policy. Additional observed chord variations were retained where
they had already been exported. No unverified meaning is assigned to higher
CV numbers.

## Live-policy extension

Three Volume 2 Main CV1 exports contain melodic accompaniment but no Bass
notes. The prior validator therefore rejected the complete library. The
explicit Ostinato policy now retains the first Main Bass note when one exists;
otherwise it uses the lowest melodic note at the earliest Main onset as the
source pitch-class anchor. A style with no Main melodic note is still rejected.
This is a local playback rule over observed MIDI events, not a claim about
KORG NTT, key, or chord-variation semantics. Drum and Percussion pitches
remain untransposed.

## Automated evidence

- Complete local suite: **201 passed**.
- Browser JavaScript checks, Ruff lint and formatting, and strict mypy: passed.
- All sixteen imported documents passed strict library loading, live section
  validation, timeline generation, non-C dominant-chord scheduling, Intro,
  both Fills, and Ending exercise through the fake-synth boundary.
- A focused regression proves that a Main CV1 without Bass uses its earliest
  low melodic onset and does not weaken the rejection of non-melodic styles.

## Deployed-software evidence

- Rebuilt and recreated the Compose service from image manifest
  `sha256:e9229d050995d7a3a2e50b1a97e7859736455cefb93edb14c3b6f02d2295ca78`.
- Compose health is **healthy** and `/api/health` returns `{"status":"ok"}` at
  `http://127.0.0.1:8765`.
- The live catalog reports exactly sixteen imported KORG entries. All eight
  new selector commands and timeline endpoints succeeded, and the transport
  was restored to stopped `modern_tango` afterward.
- The local converted directory is a bind mount at
  `/opt/ostinato-local-styles/korg` with `RW=false`. A clean container started
  from the image contained only the tracked KORG workspace README under
  `/app`; no downloaded, extracted, MIDI, JSON, or WAV derivative was baked
  into the image.
- Each new style rendered 48,000 stereo frames through the deployed MuseScore
  General HQ SoundFont. Every PCM result was 192,000 bytes and non-silent.
  This verification opened no ALSA or PipeWire output device.

## Evidence boundary and human gate

- Download provenance, extraction, official-converter export, JSON import,
  catalog selection, timeline generation, scheduling, and non-silent
  FluidSynth PCM: **observed by software**.
- Proprietary material absent from the image and read-only at runtime:
  **observed by software**.
- Original KORG sounds, authenticated NTT/key behavior, and higher-CV meaning:
  **unavailable and not claimed**.
- FR-4X MIDI behavior: **untested** because no accordion hardware is available.
- Host ALSA/PipeWire accompaniment output: **untested in this milestone**; the
  synth verification deliberately did not open an audio device.
- Musical balance, chord adaptation quality, transitions, and playability:
  **pending performer listening**.

The milestone stops at the listening gate. The deployed interface is ready for
the user to test all sixteen KORG entries.
