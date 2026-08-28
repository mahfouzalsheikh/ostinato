import assert from "node:assert/strict";
import test from "node:test";

import {
  centralStradellaColumn,
  classifyChordNotes,
  stradellaBassButtonsForPitch,
  stradellaCell,
} from "../../src/ostinato/web_static/stradella.js";

test("the documented two-bass-row layout centers C in the ninth column", () => {
  assert.deepEqual(stradellaCell(1, 8), {
    role: "bass",
    label: "C",
    rootPitchClass: 0,
  });
  assert.deepEqual(stradellaCell(0, 8), {
    role: "counterbass",
    label: "E",
    rootPitchClass: 4,
  });
  assert.equal(stradellaCell(2, 8).label, "CM");
  assert.equal(stradellaCell(3, 8).label, "Cm");
  assert.equal(stradellaCell(4, 8).label, "C7");
  assert.equal(stradellaCell(5, 8).label, "Cdim");
  assert.equal(centralStradellaColumn(0), 8);
});

test("normal chord-note transmission identifies common Stradella qualities", () => {
  assert.deepEqual(classifyChordNotes([48, 52, 55]), {
    rootPitchClass: 0,
    quality: "major",
    transmission: "notes",
  });
  assert.equal(classifyChordNotes([48, 51, 55]).quality, "minor");
  assert.equal(classifyChordNotes([48, 52, 55, 58]).quality, "seventh");
  assert.equal(classifyChordNotes([48, 51, 54], 0).quality, "diminished");
});

test("documented D-Mode chord codes are supported", () => {
  assert.deepEqual(classifyChordNotes([48]), {
    rootPitchClass: 0,
    quality: "major",
    transmission: "d-mode",
  });
  assert.deepEqual(classifyChordNotes([71]), {
    rootPitchClass: 11,
    quality: "minor",
    transmission: "d-mode",
  });
  assert.equal(classifyChordNotes([84]).quality, "diminished");
});

test("an isolated bass pitch exposes both physical-row candidates", () => {
  assert.deepEqual(stradellaBassButtonsForPitch(4), ["r2c13", "r1c9"]);
  assert.deepEqual(stradellaBassButtonsForPitch(0), ["r2c9", "r1c5"]);
});

test("recognized chord context resolves common bass-row positions", () => {
  assert.deepEqual(stradellaBassButtonsForPitch(0, 0), ["r2c9"]);
  assert.deepEqual(stradellaBassButtonsForPitch(4, 0), ["r1c9"]);
  assert.deepEqual(stradellaBassButtonsForPitch(7, 0), ["r2c10", "r1c6"]);
});
