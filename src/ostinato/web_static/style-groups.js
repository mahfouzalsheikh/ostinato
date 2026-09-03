const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

const PRIORITY_GROUPS = new Map([
  ["Built-in styles", 0],
  ["My styles", 1],
]);

export function styleGroups(styles) {
  const groups = [...new Set(styles.map((style) => style.group))];
  return groups.sort((left, right) => {
    const leftPriority = PRIORITY_GROUPS.get(left) ?? 2;
    const rightPriority = PRIORITY_GROUPS.get(right) ?? 2;
    return leftPriority - rightPriority || collator.compare(left, right);
  });
}

export function stylesInGroup(styles, group) {
  return styles
    .filter((style) => style.group === group)
    .sort((left, right) => collator.compare(left.name, right.name));
}

export function groupForStyle(styles, styleId) {
  return styles.find((style) => style.id === styleId)?.group ?? null;
}
