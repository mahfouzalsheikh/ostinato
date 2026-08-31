# W33 — researched orchestration and shared style timeline

Status: research, software, native-render, and deployed-software gates complete;
owner visual and listening gates pending.

## Scope

This milestone reviews all fourteen built-in styles against authoritative
instrumentation, rhythmic/dynamic practice, and score or notation references;
upgrades the most consequential orchestration mismatches that the licensed
sample rack can address; and adds one arrangement visualization to both the
style designer and live arranger.

The complete source matrix, score links, arrangement inferences, and documented
sample gaps are in `docs/style-orchestration-research.md`. No notation or
musical passages were copied into Ostinato.

## Implemented orchestration changes

- Added pinned CC0 VSCO 2 CE clarinet and trumpet staccato mappings and only
  their referenced samples.
- Swing Foxtrot, Motown Soul, Funk Pocket, and New Orleans Cha-Cha now use
  recorded trumpet for their answer lane.
- Alpine Polka now uses recorded clarinet answers with violin backing.
- New Orleans Cha-Cha now uses sampled piano rather than acoustic guitar for
  its chord-rhythm lane.
- Corrected direct sfizz loading of Shinyguitar. The supplied Aria bank normally
  defines its sample-directory variable; the image now resolves that same
  relative path and provides acoustic/electric controller defaults. The
  recordings are unchanged.

Nylon guitar, pedal steel, reggae organ, tenor sax/harmonica, dedicated
Brazilian percussion, and a multi-horn rack remain explicit future sample gaps.

## Timeline behavior

`style_timeline.py` derives five lanes directly from each renderer's authored
groove, accent, gate, phrase-dynamic, instrument, and mix data. The API exposes
the same JSON-safe model for built-ins and saved custom styles.

The designer redraws that model immediately when the template, phrase length,
instrument, level, note length, or drum state changes. The live surface fetches
and caches the selected style's model. Its playhead projects backend integer
ticks at the current tempo between status samples, so browser polling does not
produce a stepped cursor. No browser timing controls audio.

## Automated evidence

- Complete local suite: `166 passed`.
- Ruff lint, Ruff format check, and strict mypy: passed.
- Browser module tests: `12 passed`.
- New tests cover all fourteen timelines, event bounds, five-lane consistency,
  custom phrase/gate/palette/drum transformation, defining new instruments, API
  responses, missing-style handling, and both rendered UI containers.
- `git diff --check` and `docker compose config --quiet`: passed.

## Deployed-software evidence

- Final image build and service recreation: passed.
- Compose health: `healthy`; `/api/health` returned `{"status":"ok"}`.
- The final container contains `ClarinetStac.sfz` and `TrumpetStac.sfz`.
- Native sfizz smoke renders for Swing Foxtrot, Alpine Polka, Motown Soul, Funk
  Pocket, New Orleans Cha-Cha, Bossa Nova, and both corrected guitar presets
  returned non-silent PCM. The final Bossa/Funk validation emitted no missing
  sample or parse warning.
- Timeline API verification reports trumpet for Swing and New Orleans, clarinet
  for Polka, piano comping for New Orleans, five lanes, and populated events.
- A 1440×1200 headless Chrome capture of the deployed main surface was visually
  inspected: the five lanes, four measure boundaries, phrase-energy bars,
  instrument/level labels, and dense percussion subevents render without
  overlap or horizontal clipping at that viewport.
- Final arranger state: `running=false`, `section=stopped`, style
  `modern_tango`, synthesis engine `sfizz · open sampled genre ensemble`.

## Evidence boundary and human gate

- Physical FR-4X, mixer, amplifier, and speaker behavior: **untested**.
- Deployed main-timeline layout at 1440×1200: **observed** by headless software
  capture; designer interaction is automated/API verified but owner review is
  still **pending**.
- Perceived clarinet/trumpet/guitar realism, cross-style mix, intro/ending/fill
  quality, and playability with live accordion: **pending** performer listening.

The owner should now inspect both timelines and listen especially to Swing,
Polka, Motown, Funk, New Orleans Cha-Cha, Bossa Nova, and Reggae. That is the W33
human gate; commit/push should follow only after requested acceptance.

## Drum audibility correction

Performer feedback after the first W33 deployment found no clearly audible
drums. Native isolation confirmed that the SFZ mappings and MIDI notes worked,
but the prior shared `0.42` rack gain left several style stems around `-38` to
`-56 dBFS RMS`. Each style now has a measured sample-normalization gain before
its authored MIDI velocities. Classic Waltz receives the same correction for
its quieter brush library; Classic Tango intentionally remains kit-free.

Four-bar full-mix candidate renders for all affected styles had zero clipped
samples after reducing Polka separately for headroom. Deployed isolation then
measured Bossa drums at `-27.86 dBFS RMS` / `-10.61 dBFS` peak and Reggae at
`-33.49 dBFS RMS` / `-7.92 dBFS` peak, both with zero clipped samples. The
service remained healthy and the transport was left stopped. Perceived balance
on the physical performance route remains a listening-gate decision.

The final deployed Polka reduction is `0.75`; a complete four-bar full-mix
render measured `-16.43 dBFS RMS`, `-0.49 dBFS` peak, and zero clipped samples.
