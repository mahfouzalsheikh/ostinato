import assert from "node:assert/strict";
import test from "node:test";

import {
  groupForStyle,
  styleGroups,
  stylesInGroup,
} from "../../src/ostinato/web_static/style-groups.js";

const styles = [
  { id: "builtin", name: "Tango", group: "Latin & Tango" },
  { id: "v10-b", name: "Zulu", group: "Jazz, Swing & Blues" },
  { id: "v2-b", name: "Beta", group: "Ballads" },
  { id: "v2-a", name: "Alpha", group: "Ballads" },
  { id: "mine", name: "Mine", group: "My styles" },
];

test("groups keep personal styles first and alphabetize musical categories", () => {
  assert.deepEqual(styleGroups(styles), [
    "My styles",
    "Ballads",
    "Jazz, Swing & Blues",
    "Latin & Tango",
  ]);
});

test("styles are filtered and alphabetized within a group", () => {
  assert.deepEqual(
    stylesInGroup(styles, "Ballads").map((style) => style.id),
    ["v2-a", "v2-b"],
  );
});

test("the selected style resolves its current group", () => {
  assert.equal(groupForStyle(styles, "v10-b"), "Jazz, Swing & Blues");
  assert.equal(groupForStyle(styles, "missing"), null);
});
