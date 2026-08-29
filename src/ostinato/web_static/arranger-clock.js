export function projectedBeatIndex(status, elapsedMilliseconds = 0) {
  if (!status?.running || !Number.isInteger(status.position_ticks)) return null;
  if (!Number.isInteger(status.ticks_per_beat) || status.ticks_per_beat <= 0) return null;
  if (!Number.isInteger(status.beats_per_bar) || status.beats_per_bar <= 0) return null;

  const elapsed = Math.max(0, Number(elapsedMilliseconds) || 0);
  const tempo = Number(status.tempo_bpm);
  const projectedTicks = status.position_ticks
    + (elapsed * tempo * status.ticks_per_beat / 60_000);
  const barTicks = status.beats_per_bar * status.ticks_per_beat;
  const tickInBar = ((projectedTicks % barTicks) + barTicks) % barTicks;
  return Math.floor(tickInBar / status.ticks_per_beat);
}
