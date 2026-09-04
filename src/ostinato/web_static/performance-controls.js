export const PERFORMANCE_CONTROL_ACTIONS = [
  { action: "intro", label: "Intro" },
  { action: "fill_1", label: "Fill In 1" },
  { action: "fill_2", label: "Fill In 2" },
  { action: "ending", label: "Ending" },
  { action: "start", label: "Start" },
  { action: "stop", label: "Stop" },
];

export function isLearnableControlEvent(event) {
  if (event?.type !== "midi" || event.direction !== "in") return false;
  if (!Array.isArray(event.bytes) || event.bytes.length === 0) return false;
  if (event.bytes.some((byte) => !Number.isInteger(byte) || byte < 0 || byte > 255)) return false;
  const [status, data1] = event.bytes;
  const family = status & 0xf0;
  if ([0x80, 0x90, 0xa0, 0xd0, 0xe0].includes(family)) return false;
  if (family === 0xb0) return event.bytes.length === 3 && data1 !== 11;
  if (family === 0xc0) return event.bytes.length === 2;
  return ![0xf8, 0xfe].includes(status);
}

export function bindingsFromProfile(profile) {
  const result = new Map();
  for (const binding of profile?.performance_controls?.bindings ?? []) {
    if (!PERFORMANCE_CONTROL_ACTIONS.some(({ action }) => action === binding.action)) continue;
    result.set(binding.action, binding.messages.map((message) => [...message]));
  }
  return result;
}

export function orderedBindings(bindings) {
  return PERFORMANCE_CONTROL_ACTIONS.flatMap(({ action }) => {
    const messages = bindings.get(action);
    return messages ? [{ action, messages: messages.map((message) => [...message]) }] : [];
  });
}

export function formatMessageSequence(messages) {
  if (!messages?.length) return "Not learned";
  return messages
    .map((message) => message.map((byte) => byte.toString(16).padStart(2, "0")).join(" "))
    .join("  ·  ");
}
