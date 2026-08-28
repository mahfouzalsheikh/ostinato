import "./fr4x-accordion.js";

const $ = (selector) => document.querySelector(selector);
const accordion = $("#accordion");
const socketLed = $("#socket-led");
const socketState = $("#socket-state");
const rateOutput = $("#event-rate");
const messageOutput = $("#connection-message");
const inputSelect = $("#midi-input");
const outputSelect = $("#midi-output");
const trebleInput = $("#treble-input-channel");
const trebleOutput = $("#treble-output-channel");
const trebleBase = $("#treble-base-note");
const velocity = $("#simulator-velocity");
const velocityValue = $("#velocity-value");
const mappingState = $("#mapping-state");
const bindingCount = $("#binding-count");
const learnButton = $("#learn-left");
const learnMessage = $("#learn-message");
const eventList = $("#event-list");
const readout = $("#transport-readout");

const STORAGE_MAPPING = "ostinato.web.mapping.v1";
const STORAGE_BINDINGS = "ostinato.web.left-bindings.v1";
const MAX_EVENTS = 60;

let socket;
let reconnectTimer;
let eventsThisSecond = 0;
let learning = false;
let portStatus = null;

function channelOptions(label) {
  const fragment = document.createDocumentFragment();
  fragment.append(new Option(label, ""));
  for (let channel = 1; channel <= 16; channel += 1) {
    fragment.append(new Option(`Channel ${channel}`, String(channel)));
  }
  return fragment;
}

trebleInput.append(channelOptions("Not mapped"));
trebleOutput.append(channelOptions("No output channel"));

function loadJson(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}

const savedMapping = loadJson(STORAGE_MAPPING, {});
trebleInput.value = savedMapping.inputChannel ?? "";
trebleOutput.value = savedMapping.outputChannel ?? "";
trebleBase.value = savedMapping.baseNote ?? "";
velocity.value = savedMapping.velocity ?? 96;
velocityValue.value = velocity.value;
accordion.setBindings(loadJson(STORAGE_BINDINGS, {}));
updateMappingState();
updateBindingCount();

function mapping() {
  const numberOrNull = (value) => value === "" ? null : Number(value);
  return {
    inputChannel: numberOrNull(trebleInput.value),
    outputChannel: numberOrNull(trebleOutput.value),
    baseNote: numberOrNull(trebleBase.value),
    velocity: Number(velocity.value),
  };
}

function saveMapping() {
  localStorage.setItem(STORAGE_MAPPING, JSON.stringify(mapping()));
  updateMappingState();
}

function updateMappingState() {
  const value = mapping();
  const ready = value.inputChannel != null && value.baseNote != null;
  mappingState.textContent = ready ? "Input mapped" : "Unmapped";
  mappingState.classList.toggle("ready", ready);
}

function updateBindingCount() {
  const count = Object.keys(accordion.bindings ?? {}).length;
  bindingCount.textContent = `${count} learned`;
  bindingCount.classList.toggle("ready", count > 0);
}

function setSocketState(state, label) {
  socketLed.className = `led ${state}`;
  socketState.textContent = label;
}

function connectSocket() {
  clearTimeout(reconnectTimer);
  setSocketState("", "Connecting");
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  socket = new WebSocket(`${protocol}//${location.host}/ws/midi`);
  socket.addEventListener("open", () => setSocketState("live", "Live"));
  socket.addEventListener("message", ({ data }) => {
    try {
      handleServerEvent(JSON.parse(data));
    } catch (error) {
      showMessage(`Invalid server event: ${error}`, true);
    }
  });
  socket.addEventListener("close", () => {
    setSocketState("error", "Reconnecting");
    reconnectTimer = setTimeout(connectSocket, 1500);
  });
  socket.addEventListener("error", () => setSocketState("error", "Socket error"));
}

function send(command) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    showMessage("The real-time connection is not ready.", true);
    return false;
  }
  socket.send(JSON.stringify(command));
  return true;
}

function handleServerEvent(event) {
  if (event.type === "status") {
    portStatus = event;
    populatePorts(event);
    updateConnectionMessage(event);
    return;
  }
  if (event.type === "error") {
    showMessage(event.message, true);
    return;
  }
  if (event.type !== "midi") return;

  eventsThisSecond += 1;
  accordion.applyMidi(event, mapping());
  const learned = accordion.learnFromEvent(event);
  if (learned) {
    localStorage.setItem(STORAGE_BINDINGS, JSON.stringify(accordion.bindings));
    updateBindingCount();
    learnMessage.textContent = `Learned ${learned.id} from MIDI ${learned.signature}. Select another button or turn Learn off.`;
  }
  appendEvent(event);
  updateReadout(event);
}

function populatePorts(status) {
  replaceOptions(inputSelect, "No input selected", status.inputs, status.selected_input);
  replaceOptions(outputSelect, "No output selected", status.outputs, status.selected_output);
}

function replaceOptions(select, emptyLabel, names, selected) {
  const current = selected ?? select.value;
  select.replaceChildren(new Option(emptyLabel, ""));
  for (const name of names) select.append(new Option(name, name));
  if ([...select.options].some((option) => option.value === current)) select.value = current;
}

function updateConnectionMessage(status) {
  if (status.error) {
    showMessage(status.error, true);
    return;
  }
  const input = status.input_connected ? "input connected" : "input idle";
  const output = status.output_connected ? "output connected" : "output idle";
  showMessage(`${input}; ${output}. Port names are selected explicitly.`);
}

function showMessage(message, error = false) {
  messageOutput.textContent = message;
  messageOutput.classList.toggle("error", error);
}

function appendEvent(event) {
  eventList.querySelector(".empty-event")?.remove();
  const item = document.createElement("li");
  const direction = event.direction === "in" ? "IN" : "OUT";
  item.innerHTML = `
    <strong class="direction-${event.direction}">${direction}</strong>
    <span>${escapeHtml(event.message_type)}</span>
    <span>${event.channel == null ? "system" : `ch ${event.channel}`}</span>
    <span class="event-port">${escapeHtml(event.port)}</span>
    <span class="event-bytes">${event.bytes.map((byte) => byte.toString(16).padStart(2, "0")).join(" ")}</span>
  `;
  eventList.prepend(item);
  while (eventList.children.length > MAX_EVENTS) eventList.lastElementChild.remove();
}

function escapeHtml(value) {
  const span = document.createElement("span");
  span.textContent = String(value);
  return span.innerHTML;
}

function updateReadout(event) {
  const detail = event.note == null
    ? event.message_type
    : `${event.message_type} · note ${event.note} · velocity ${event.velocity}`;
  readout.querySelector("strong").textContent = detail;
  readout.querySelector("code").textContent = `${event.direction.toUpperCase()} · ${event.port} · ch ${event.channel ?? "—"}`;
}

function sendNote(channel, note, active) {
  if (!portStatus?.output_connected) {
    showMessage("Select and connect a MIDI output before using the simulator.", true);
    return;
  }
  const status = (active ? 0x90 : 0x80) | (channel - 1);
  send({ type: "midi.send", bytes: [status, note, active ? mapping().velocity : 0] });
}

$("#apply-ports").addEventListener("click", () => {
  send({
    type: "ports.select",
    input: inputSelect.value || null,
    output: outputSelect.value || null,
  });
});

$("#refresh-ports").addEventListener("click", () => send({ type: "status.request" }));

for (const control of [trebleInput, trebleOutput, trebleBase, velocity]) {
  control.addEventListener("input", () => {
    velocityValue.value = velocity.value;
    saveMapping();
  });
}

accordion.addEventListener("surface-note", ({ detail }) => {
  const value = mapping();
  if (value.outputChannel == null || value.baseNote == null) {
    if (detail.active) showMessage("Set a simulator output channel and leftmost key note first.", true);
    return;
  }
  const note = value.baseNote + detail.index;
  if (note > 127) {
    showMessage("The mapped piano range exceeds MIDI note 127.", true);
    return;
  }
  sendNote(value.outputChannel, note, detail.active);
});

accordion.addEventListener("surface-bass", ({ detail }) => {
  sendNote(detail.channel, detail.note, detail.active);
});

accordion.addEventListener("learn-target", ({ detail }) => {
  learnMessage.textContent = `Waiting for the physical event for ${detail.id}…`;
});

accordion.addEventListener("unmapped-button", ({ detail }) => {
  learnMessage.textContent = `${detail.id} has no learned MIDI event. Turn Learn on to bind it.`;
});

learnButton.addEventListener("click", () => {
  learning = !learning;
  accordion.setLearning(learning);
  learnButton.classList.toggle("active", learning);
  learnButton.textContent = learning ? "Learning on" : "Learn";
  learnMessage.textContent = learning
    ? "Click a visual left-hand button, then press its physical counterpart."
    : "Learning is off.";
});

$("#clear-left").addEventListener("click", () => {
  if (!window.confirm("Clear all browser-local left-hand bindings?")) return;
  accordion.setBindings({});
  localStorage.removeItem(STORAGE_BINDINGS);
  updateBindingCount();
  learnMessage.textContent = "All browser-local bindings were cleared.";
});

$("#clear-events").addEventListener("click", () => {
  eventList.innerHTML = '<li class="empty-event">No MIDI events received.</li>';
});

setInterval(() => {
  rateOutput.textContent = `${eventsThisSecond} msg/s`;
  eventsThisSecond = 0;
}, 1000);

connectSocket();

