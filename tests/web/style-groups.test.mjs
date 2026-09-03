import assert from "node:assert/strict";
import test from "node:test";

import {
  groupForStyle,
  styleGroups,
  stylesInGroup,
} from "../../src/ostinato/web_static/style-groups.js";

const styles = [
  { id: "builtin", name: "Tango", group: "Built-in styles" },
  { id: "v10-b", name: "Zulu", group: "KORG Styles · Volume 10" },
  { id: "v2-b", name: "Beta", group: "KORG Styles · Volume 2" },
  { id: "v2-a", name: "Alpha", group: "KORG Styles · Volume 2" },
  { id: "mine", name: "Mine", group: "My styles" },
];

test("groups keep product groups first and sort KORG volumes naturally", () => {
  assert.deepEqual(styleGroups(styles), [
    "Built-in styles",
    "My styles",
    "KORG Styles · Volume 2",
    "KORG Styles · Volume 10",
  ]);
});

test("styles are filtered and alphabetized within a group", () => {
  assert.deepEqual(
    stylesInGroup(styles, "KORG Styles · Volume 2").map((style) => style.id),
    ["v2-a", "v2-b"],
  );
});

test("the selected style resolves its current group", () => {
  assert.equal(groupForStyle(styles, "v10-b"), "KORG Styles · Volume 10");
  assert.equal(groupForStyle(styles, "missing"), null);
});
