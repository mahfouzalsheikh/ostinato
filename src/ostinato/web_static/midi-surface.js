export const PIANO_KEY_COUNT = 37;
export const PIANO_FIRST_PITCH_CLASS = 5; // F, matching the physical shape.

export function inferPianoBase(notes) {
  const observed = [...new Set(notes)].filter(
    (note) => Number.isInteger(note) && note >= 0 && note <= 127,
  );
  if (!observed.length) return null;
  const low = Math.min(...observed);
  const high = Math.max(...observed);
  const midpointTarget = ((low + high) / 2) - ((PIANO_KEY_COUNT - 1) / 2);
  const candidates = [];
  for (
    let base = PIANO_FIRST_PITCH_CLASS;
    base + PIANO_KEY_COUNT - 1 <= 127;
    base += 12
  ) {
    if (base <= low && high <= base + PIANO_KEY_COUNT - 1) candidates.push(base);
  }
  if (candidates.length) {
    return candidates.reduce((best, candidate) => (
      Math.abs(candidate - midpointTarget) < Math.abs(best - midpointTarget)
        ? candidate
        : best
    ));
  }
  return low - (((low - PIANO_FIRST_PITCH_CLASS) % 12) + 12) % 12;
}
