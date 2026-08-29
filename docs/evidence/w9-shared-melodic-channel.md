# W9 — Shared Bass/Chord receive channel

## Milestone boundary

W9 removes the incorrect assumption that accompaniment Bass and Chord must use
different FR-4X receive channels. The guided wizard can confirm the same channel
for both melodic roles while still requiring separate audible probes. Drum must
remain on a different channel because its note map has percussion semantics.
An explicit **Shared Orchestra Part** mode begins at Bass 4, Chord 4, and Drum
10 so the reported topology does not require stepping through unrelated
candidates.

## Observed

- **observed, user-reported:** the connected FR-4X setup requires channel 4 for
  both arranger Bass and Chord. The W8 wizard prevented that route by removing a
  channel after its first confirmation.
- **pending:** repeat both channel-4 audible probes and confirm that arranger
  bass and chord patterns sound through the intended single FR-4X part.
- **observed, software only:** the rebuilt Compose service is healthy with
  arranger output still unconfigured. No live probe endpoint was called during
  verification, so this does not claim acoustic channel-4 behavior.
- **observed, software only:** the live routing API exposes Shared Orchestra
  Part with Bass 4, Chord 4, and Drum 10 as its probe starting points.

No shared channel is committed as a project default. Channel 4 is accepted only
after the live wizard separately probes and the performer confirms Bass and
Chord on that channel.

## Automated

- Routing validation accepts Bass 4, Chord 4, and Drum 10.
- Routing validation rejects a Drum channel that equals either melodic channel.
- Planner tests verify that low bass notes and upper chord voicings are both
  emitted on MIDI channel 4 while drums remain on channel 10.
- FastAPI tests verify that two independent probe confirmations can approve the
  shared channel-4 route.

## Musical limitation

A MIDI channel addresses one FR-4X part. When Bass and Chord share channel 4,
both patterns use that part's one selected timbre and part-level settings.
Ostinato can sequence different pitches and rhythms, but it cannot provide two
independent native timbres on the shared channel. The review step discloses this
before saving.

## Safety

The change adds no new message types. Probes and playback still send bounded
note-on/note-off messages with owner-scoped cleanup; no program, bank, volume,
pan, or System Exclusive messages are introduced. FR-4X analog audio stays on
its direct mixer path.
