# W8 — Guided FR-4X output probe

## Milestone boundary

W8 replaces manual accompaniment-channel selection with a three-step guided
wizard: prepare the FR-4X and exact output, audibly probe Bass/Chord/Drum parts,
then review and save. It supports both documented native Bass/Chord parts and
separate Orchestra Bass/Chord parts. It does not claim automatic acoustic
classification or change FR-4X settings through undocumented System Exclusive.

## Documented

- Roland lists Bass/Free Bass, Chord, Orchestra Bass, Orchestra Chord, and Drum
  as separate MIDI parts, with documented defaults 2, 3, 5, 6, and 10.
- External Seq. Playback exposes Bass & Chord as one keyboard-disconnect group;
  this grouping is not treated as one receive channel.
- MIDI messages do not report the identity of the internal sound heard by the
  performer. Audible confirmation remains a human hardware observation.

Sources: [FR-4X Reference Manual](https://static.roland.com/assets/media/pdf/FR-4x_reference_e01_W.pdf)
and [FR-4X MIDI Implementation](https://static.roland.com/assets/media/pdf/FR-4x_MIDI_Implementation_e01_W.pdf).

## Automated

- Registry tests cover the native/orchestral documented starting points,
  matching part/channel/output evidence, expiry, and one-time consumption.
- FastAPI tests cover three required probes, channel-role validation,
  mismatched-probe rejection, bounded note cleanup, atomic routing persistence,
  exact output restoration, and live arranger dispatch after guided setup.
- Static asset tests verify the Prepare/Detect/Save controls and absence of the
  old manual bass-channel selector.
- All automated output uses an in-memory MIDI backend. It does not imply that
  the physical FR-4X generated sound.

## Observed

- The rebuilt Compose service reported healthy with the exact connected FR-4X
  input/output name restored and arranger output still unconfigured.
- The live routing API returned native 2/3/10 and orchestral 5/6/10 only as
  unconfirmed documented starting points.
- Headless Chrome rendered the Prepare and Detect steps at desktop size. The
  wizard selected the exact observed FR-4X output, defaulted to native mode,
  entered Bass detection on channel 2, and kept **Yes, correct part** disabled
  before a probe. A clean reload produced no browser exception.
- No `POST /api/arranger/probe` request was made against the live container, so
  no test or arranger note was sent to the physical FR-4X during this check.

## Pending human gate

- Open **Sound module setup** with the physical FR-4X connected.
- Enable only the required External Seq. Playback groups and select the intended
  native or orchestral mode.
- For Bass, Chord, and Drum, report **Yes, correct part** only after hearing the
  requested internal part; use **try next** for silence or a wrong part.
- Save the review, restart the service, and confirm the exact output and route
  restore.
- Start each style and assess the native sounds, balance, response, transitions,
  and note cleanup. Record any wrong-part response by requested part and tested
  channel.

## Safety

Probes are short note-on sequences followed by owner-scoped note release. Route
changes stop a running arranger and output changes release active notes. The
wizard sends no program, bank, volume, pan, or System Exclusive messages. The
FR-4X analog output remains on its direct mixer path.
