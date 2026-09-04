import assert from "node:assert/strict";
import test from "node:test";

import {
  bindingsFromProfile,
  formatMessageSequence,
  isLearnableControlEvent,
  orderedBindings,
} from "../../src/ostinato/web_static/performance-controls.js";

function event(bytes, overrides = {}) {
  return { type: "midi", direction: "in", bytes, ...overrides };
}

test("learning accepts discrete controls and excludes performance traffic", () => {
  assert.equal(isLearnableControlEvent(event([0xfa])), true);
  assert.equal(isLearnableControlEvent(event([0xb0, 64, 127])), true);
  assert.equal(isLearnableControlEvent(event([0xc0, 3])), true);
  assert.equal(isLearnableControlEvent(event([0x90, 60, 100])), false);
  assert.equal(isLearnableControlEvent(event([0xb0, 11, 70])), false);
  assert.equal(isLearnableControlEvent(event([0xf8])), false);
  assert.equal(isLearnableControlEvent(event([0xfe])), false);
  assert.equal(isLearnableControlEvent(event([0xfa], { direction: "out" })), false);
});

test("saved bindings round trip in stable arranger-action order", () => {
  const profile = {
    performance_controls: {
      bindings: [
        { action: "stop", messages: [[0xfc]] },
        { action: "intro", messages: [[0xfa]] },
      ],
    },
  };
  const bindings = bindingsFromProfile(profile);

  assert.deepEqual(orderedBindings(bindings), [
    { action: "intro", messages: [[0xfa]] },
    { action: "stop", messages: [[0xfc]] },
  ]);
});

test("message fingerprints are displayed as exact hexadecimal sequences", () => {
  assert.equal(formatMessageSequence(), "Not learned");
  assert.equal(
    formatMessageSequence([[0xb0, 64, 127], [0xc0, 3]]),
    "b0 40 7f  ·  c0 03",
  );
});
