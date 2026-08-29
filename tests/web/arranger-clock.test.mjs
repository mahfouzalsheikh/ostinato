import assert from "node:assert/strict";
import test from "node:test";

import { projectedBeatIndex } from "../../src/ostinato/web_static/arranger-clock.js";

const status = (overrides = {}) => ({
  running: true,
  tempo_bpm: 120,
  beats_per_bar: 4,
  ticks_per_beat: 96,
  position_ticks: 0,
  ...overrides,
});

test("four-four advances one light per quarter-note beat", () => {
  assert.equal(projectedBeatIndex(status(), 0), 0);
  assert.equal(projectedBeatIndex(status(), 500), 1);
  assert.equal(projectedBeatIndex(status(), 1_000), 2);
  assert.equal(projectedBeatIndex(status(), 1_500), 3);
  assert.equal(projectedBeatIndex(status(), 2_000), 0);
});

test("meter controls the number of steps before the downbeat wraps", () => {
  assert.equal(projectedBeatIndex(status({ beats_per_bar: 3 }), 1_000), 2);
  assert.equal(projectedBeatIndex(status({ beats_per_bar: 3 }), 1_500), 0);
  assert.equal(projectedBeatIndex(status({ beats_per_bar: 2 }), 1_000), 0);
});

test("backend tick samples re-anchor interpolation after tempo changes", () => {
  const reanchored = status({ tempo_bpm: 60, position_ticks: 3 * 96 });

  assert.equal(projectedBeatIndex(reanchored, 0), 3);
  assert.equal(projectedBeatIndex(reanchored, 1_000), 0);
});

test("stopped or incomplete status has no active beat", () => {
  assert.equal(projectedBeatIndex(status({ running: false }), 500), null);
  assert.equal(projectedBeatIndex(status({ position_ticks: null }), 500), null);
});
