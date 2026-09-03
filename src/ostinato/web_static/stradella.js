export const STRADELLA_COLUMN_COUNT = 20;
export const STRADELLA_ROW_COUNT = 6;

const FUNDAMENTAL_LABELS = [
  "E", "B", "F♯", "C♯", "A♭", "E♭", "B♭", "F", "C", "G",
  "D", "A", "E", "B", "F♯", "C♯", "A♭", "E♭", "B♭", "F",
];
const FUNDAMENTAL_PITCH_CLASSES = [
  4, 11, 6, 1, 8, 3, 10, 5, 0, 7,
  2, 9, 4, 11, 6, 1, 8, 3, 10, 5,
];
const COUNTERBASS_LABELS = [
  "A♭", "E♭", "B♭", "F", "C", "G", "D", "A", "E", "B",
  "F♯", "C♯", "A♭", "E♭", "B♭", "F", "C", "G", "D", "A",
];

export const STRADELLA_ROWS = [
  { id: "counterbass", label: "Counterbass" },
  { id: "bass", label: "Fundamental bass" },
  { id: "major", label: "Major" },
  { id: "minor", label: "Minor" },
  { id: "seventh", label: "Dominant seventh" },
  { id: "diminished", label: "Diminished" },
];

export function stradellaCell(row, column) {
  if (row < 0 || row >= STRADELLA_ROW_COUNT) return null;
  if (column < 0 || column >= STRADELLA_COLUMN_COUNT) return null;
  const rootPitchClass = FUNDAMENTAL_PITCH_CLASSES[column];
  const rootLabel = FUNDAMENTAL_LABELS[column];
  if (row === 0) {
    return {
      role: "counterbass",
      label: COUNTERBASS_LABELS[column],
      rootPitchClass: (rootPitchClass + 4) % 12,
    };
  }
  if (row === 1) return { role: "bass", label: rootLabel, rootPitchClass };
  const quality = STRADELLA_ROWS[row].id;
  const suffix = { major: "M", minor: "m", seventh: "7", diminished: "dim" }[quality];
  return { role: quality, label: `${rootLabel}${suffix}`, rootPitchClass };
}

export function centralStradellaColumn(rootPitchClass) {
  const matches = FUNDAMENTAL_PITCH_CLASSES
    .map((pitchClass, index) => ({ pitchClass, index }))
    .filter((item) => item.pitchClass === rootPitchClass);
  if (!matches.length) return null;
  return matches.reduce((best, candidate) => (
    Math.abs(candidate.index - 8) < Math.abs(best.index - 8)
      ? candidate
      : best
  )).index;
}

export function stradellaBassButtonsForPitch(pitchClass, chordRootPitchClass = null) {
  if (!Number.isInteger(pitchClass)) return [];
  const normalizedPitch = ((pitchClass % 12) + 12) % 12;
  const fundamentalColumn = centralStradellaColumn(normalizedPitch);
  const counterbassRoot = (normalizedPitch + 8) % 12;
  const counterbassColumn = centralStradellaColumn(counterbassRoot);
  if (fundamentalColumn == null || counterbassColumn == null) return [];

  const candidates = {
    fundamental: `r2c${fundamentalColumn + 1}`,
    counterbass: `r1c${counterbassColumn + 1}`,
  };
  if (Number.isInteger(chordRootPitchClass)) {
    const chordRoot = ((chordRootPitchClass % 12) + 12) % 12;
    if (normalizedPitch === chordRoot) return [candidates.fundamental];
    if (normalizedPitch === (chordRoot + 4) % 12) return [candidates.counterbass];
  }
  return [candidates.fundamental, candidates.counterbass];
}

const CHORD_PATTERNS = [
  { quality: "seventh", intervals: [0, 4, 7, 10] },
  { quality: "seventh", intervals: [0, 4, 10] },
  { quality: "diminished", intervals: [0, 3, 6, 9] },
  { quality: "diminished", intervals: [0, 3, 6] },
  { quality: "major", intervals: [0, 4, 7] },
  { quality: "minor", intervals: [0, 3, 7] },
];

function pitchClassMask(notes) {
  return notes.reduce((mask, note) => mask | (1 << (note % 12)), 0);
}

const CLASSIFIED_CHORDS = new Map();
for (const [priority, pattern] of CHORD_PATTERNS.entries()) {
  for (let rootPitchClass = 0; rootPitchClass < 12; rootPitchClass += 1) {
    const mask = pitchClassMask(
      pattern.intervals.map((interval) => rootPitchClass + interval),
    );
    const existing = CLASSIFIED_CHORDS.get(mask);
    if (existing && existing.priority !== priority) continue;
    const entry = existing ?? { priority, chords: [] };
    entry.chords.push({
      rootPitchClass,
      quality: pattern.quality,
      transmission: "notes",
    });
    CLASSIFIED_CHORDS.set(mask, entry);
  }
}

export function classifyChordNotes(notes, preferredRoot = null) {
  const valid = notes.filter((note) => Number.isInteger(note) && note >= 0 && note <= 127);
  if (!valid.length) return null;
  if (valid.length === 1 && valid[0] >= 48 && valid[0] <= 95) {
    const offset = valid[0] - 48;
    const quality = ["major", "minor", "seventh", "diminished"][Math.floor(offset / 12)];
    return { rootPitchClass: offset % 12, quality, transmission: "d-mode" };
  }

  const entry = CLASSIFIED_CHORDS.get(pitchClassMask(valid));
  if (!entry) return null;
  return entry.chords.find((chord) => chord.rootPitchClass === preferredRoot)
    ?? entry.chords[0];
}
