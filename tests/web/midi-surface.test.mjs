import assert from "node:assert/strict";
import test from "node:test";

import {
  PIANO_FIRST_PITCH_CLASS,
  PIANO_KEY_COUNT,
  inferPianoBase,
} from "../../src/ostinato/web_static/midi-surface.js";

test("the observed FR-4X sample is centered in an F-aligned keyboard", () => {
  const base = inferPianoBase([62, 64, 65, 67, 71]);

  assert.equal(base, 53);
  assert.equal(72 - base, 19);
  assert.equal((PIANO_FIRST_PITCH_CLASS + (72 - base)) % 12, 0);
});

test("physical range endpoints determine the exact keyboard origin", () => {
  const base = inferPianoBase([53, 91]);

  assert.equal(PIANO_KEY_COUNT, 39);
  assert.equal(base, 53);
  assert.equal(base + PIANO_KEY_COUNT - 1, 91);
  assert.equal((PIANO_FIRST_PITCH_CLASS + PIANO_KEY_COUNT - 1) % 12, 7);
});

test("no observed notes leaves the keyboard unconfigured", () => {
  assert.equal(inferPianoBase([]), null);
});
