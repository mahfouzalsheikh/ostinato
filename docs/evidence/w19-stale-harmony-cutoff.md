# W19 stale harmony cutoff evidence

Status: automated software evidence; deployed hardware listening test pending.

This change fixed stale chord overlap but did not resolve the separately
reported off-tune brass/reed timbre. That fault is addressed in W20.

## Problem isolated

Every generated melodic MIDI note was already constrained to the recognized
chord, but chord changes used MIDI CC123 (All Notes Off). CC123 follows the
sample preset's release envelope. With the deployed TimGM6mb string preset, an
isolated measurement showed the old chord's RMS level remained 14,958 during
the first 100 ms after CC123 and was still 1,234 after 600 ms.

The same measurement using CC120 (All Sound Off) reduced the first 100 ms to
2,340 RMS and the 600 ms value to 30. The measurement used a separate
FluidSynth instance in the deployed container and did not exercise the FR-4X
or the Bluetooth output path.

## Change

Live harmony changes now send CC120 before CC123 on all four melodic synth
channels. This cuts voices from the preceding chord before scheduling the new
chord while retaining CC123 for note-state cleanup. Drum voices are not cut.

## Verification

- The unit test for next-chunk harmony changes now requires CC120 and CC123 on
  every melodic channel.
- Full local software suite: passed (`126 passed`, formatting and type checks
  passed).
- Container rebuild/restart: passed; `ostinato-ostinato-1` reports healthy and
  the arranger status endpoint reports FluidSynth configured with no error.
- Subjective FR-4X/Bluetooth listening test: pending user confirmation.
