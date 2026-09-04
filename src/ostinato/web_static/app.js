import "./fr4x-accordion.js?v=11";
import { projectedBeatIndex } from "./arranger-clock.js?v=1";
import {
  PERFORMANCE_CONTROL_ACTIONS,
  bindingsFromProfile,
  formatMessageSequence,
  isLearnableControlEvent,
  orderedBindings,
} from "./performance-controls.js?v=2";
import { groupForStyle, styleGroups, stylesInGroup } from "./style-groups.js?v=1";

const $ = (selector) => document.querySelector(selector);
const accordion = $("#accordion");
const socketLed = $("#socket-led");
const socketState = $("#socket-state");
const rateOutput = $("#event-rate");
const messageOutput = $("#connection-message");
const inputSelect = $("#midi-input");
const outputSelect = $("#midi-output");
const eventList = $("#event-list");
const readout = $("#transport-readout");
const wizard = $("#midi-wizard");
const performanceControlDialog = $("#performance-control-dialog");
const arrangerStyleGroup = $("#arranger-style-group");
const arrangerStyle = $("#arranger-style");
const arrangerMessage = $("#arranger-message");
const fixedTempo = $("#arranger-fixed-tempo");
const audioOutputDialog = $("#audio-output-dialog");
const styleDesignerDialog = $("#style-designer-dialog");
const styleDesignerForm = $("#style-designer-form");
const designerStyleSelect = $("#designer-style-select");
const beatLights = $("#arranger-beat-lights");
const beatLabel = $("#arranger-beat-label");
const liveStyleTimeline = $("#arranger-style-timeline");
const designerStyleTimeline = $("#designer-style-timeline");

const MAX_EVENTS = 60;
const SIMULATOR_VELOCITY = 96;
const ROLE_ORDER = ["treble", "bass", "chord"];
const ROLE_COPY = {
  treble: {
    kicker: "Right keyboard · treble",
    title: "Play several right-hand piano keys",
    instructions: "Play the physical lowest and highest keys, plus several keys in between.",
    next: "Next: bass buttons",
  },
  bass: {
    kicker: "Left keyboard · bass",
    title: "Play several single bass buttons",
    instructions: "Use bass/root buttons only. Avoid chord buttons during this capture.",
    next: "Next: chord buttons",
  },
  chord: {
    kicker: "Left keyboard · chords",
    title: "Play several chord buttons",
    instructions: "Use a varied group of chord buttons. Ostinato records activity, not chord meaning.",
    next: "Review detection",
  },
};

let socket;
let reconnectTimer;
let eventsThisSecond = 0;
let portStatus = null;
let midiProfile = null;
let profileLoaded = false;
let profileRestoreAttempted = false;
let firstRunWizardShown = false;
let wizardStep = 1;
let captureIndex = 0;
let capturing = false;
let captures = freshCaptures();
let detection = null;
let performanceControlBindings = new Map();
let learningControlAction = null;
let learnedControlMessages = [];
let controlQuietTimer = null;
let controlMaximumTimer = null;
let arrangerStatus = null;
let beatClock = null;
let styleDesignerCatalog = null;
let designerDeleteArmed = false;
let designerPreviewing = false;
let designerPreviewRestartTimer = null;
let liveTimelineStyleId = null;
let browsingStyleGroup = null;
let lastArrangerStyleId = null;
const styleTimelineCache = new Map();

const DESIGNER_PREVIEW_RESTART_DELAY_MS = 180;
const CONTROL_CAPTURE_QUIET_MS = 120;
const CONTROL_CAPTURE_MAXIMUM_MS = 400;
const CONTROL_CAPTURE_MAX_MESSAGES = 8;
const DESIGNER_NON_AUDIO_FIELDS = new Set([
  "designer-name",
  "designer-preview-tempo",
  "designer-style-select",
]);

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
    cancelPerformanceLearning(false);
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
    restoreSavedPorts();
    updateConnectionSummary();
    maybeShowFirstRunWizard();
    return;
  }
  if (event.type === "error") {
    showMessage(event.message, true);
    return;
  }
  if (event.type !== "midi") return;

  eventsThisSecond += 1;
  capturePerformanceControl(event);
  captureIncomingNote(event);
  accordion.applyMidi(event);
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

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `${response.status} ${response.statusText}`);
  }
  return response.status === 204 ? null : response.json();
}

async function loadArrangerStatus() {
  try {
    renderArrangerStatus(await api("/api/arranger/status"));
  } catch (error) {
    setArrangerMessage(`Could not load arranger status: ${error.message}`, true);
  }
}

async function arrangerCommand(action, value = null) {
  try {
    const status = await api("/api/arranger/command", {
      method: "POST",
      body: JSON.stringify({ action, value }),
    });
    renderArrangerStatus(status);
  } catch (error) {
    setArrangerMessage(error.message, true);
  }
}

function renderArrangerStatus(status) {
  arrangerStatus = status;
  beatClock = { status, sampledAtMilliseconds: performance.now() };
  const groups = styleGroups(status.styles);
  const groupSignature = groups.join(":");
  if (arrangerStyleGroup.dataset.options !== groupSignature) {
    arrangerStyleGroup.replaceChildren(...groups.map((group) => new Option(group, group)));
    arrangerStyleGroup.dataset.options = groupSignature;
  }
  if (lastArrangerStyleId !== status.style) {
    browsingStyleGroup = groupForStyle(status.styles, status.style);
    lastArrangerStyleId = status.style;
  }
  if (!groups.includes(browsingStyleGroup)) browsingStyleGroup = groups[0] ?? null;
  arrangerStyleGroup.value = browsingStyleGroup ?? "";
  populateArrangerStyles(status.styles, browsingStyleGroup, status.style);
  arrangerStyleGroup.disabled = status.running;
  arrangerStyle.disabled = status.running;
  $("#open-style-designer").disabled = status.running;
  $("#arranger-tempo").textContent = status.tempo_bpm;
  $("#arranger-tempo-source").textContent = status.tempo_source;
  const fixed = status.tempo_mode === "fixed";
  const tempoMode = $("#arranger-tempo-mode");
  tempoMode.textContent = fixed ? "Fixed" : "Left-hand auto";
  tempoMode.setAttribute("aria-pressed", String(fixed));
  fixedTempo.disabled = !fixed;
  if (document.activeElement !== fixedTempo) fixedTempo.value = status.tempo_bpm;
  updateTempoKnob(Number(fixedTempo.value));
  $("#arranger-chord").textContent = status.chord ?? "No chord";
  $("#arranger-meter").textContent = `${status.beats_per_bar}/4 · ${styleName(status.style)} · ${status.synthesis_engine}`;
  const section = status.section.replaceAll("_", " ");
  $("#arranger-section").textContent = section;
  const liveState = $(".arranger-live-state");
  liveState.classList.toggle("running", status.running && status.section !== "ending");
  liveState.classList.toggle("ending", status.section === "ending");
  $("#arranger-start").disabled = status.running || !status.output_configured;
  $("#arranger-intro").disabled = !status.output_configured;
  $("#arranger-stop").disabled = !status.running;
  $("#arranger-ending").disabled = !status.running;
  const fillAvailable = status.running && status.section === "main";
  $("#arranger-fill-1").disabled = !fillAvailable;
  $("#arranger-fill-2").disabled = !fillAvailable;
  $("#arranger-fill-1").setAttribute("aria-pressed", String(status.fill_variation === 1));
  $("#arranger-fill-2").setAttribute("aria-pressed", String(status.fill_variation === 2));
  $("#arranger-sync").setAttribute("aria-pressed", String(status.sync_enabled));
  renderBeatIndicator(status, 0);
  renderImportedStyleControls(status);
  const selectedSection = status.style_controls?.active_section ?? "variation_1";
  ensureLiveStyleTimeline(status.style, selectedSection);
  if (styleDesignerDialog.open) renderDesignerPreviewState(status);

  if (status.error) {
    setArrangerMessage(status.error, true);
  } else if (!status.output_configured) {
    setArrangerMessage("Choose the analog accompaniment audio output before starting.", true);
  } else if (status.bass_channel == null || status.chord_channel == null) {
    setArrangerMessage("Run MIDI setup before using bass tempo or left-hand sync.");
  } else if (fixed) {
    setArrangerMessage(`Tempo is fixed at ${status.tempo_bpm} BPM. Drag the knob or use arrow keys to change it.`);
  } else if (status.sync_enabled) {
    setArrangerMessage(
      `Left-hand sync is on: start on bass/chord activity and stop after ${status.sync_stop_bars} silent bars.`,
    );
  } else {
    setArrangerMessage("Bass tempo is style-normalized. Switch to Fixed if you do not want strokes to change it.");
  }
}

function populateArrangerStyles(styles, group, selectedId = null) {
  const groupedStyles = stylesInGroup(styles, group);
  const optionSignature = `${group}:${groupedStyles.map((style) => style.id).join(":")}`;
  if (arrangerStyle.dataset.options !== optionSignature) {
    arrangerStyle.replaceChildren(...groupedStyles.map((style) => {
      const suffix = style.custom ? " · Custom" : "";
      const option = new Option(`${style.name} · ${style.beats_per_bar}/4${suffix}`, style.id);
      option.title = style.description ?? "";
      return option;
    }));
    arrangerStyle.dataset.options = optionSignature;
  }
  if (groupedStyles.some((style) => style.id === selectedId)) arrangerStyle.value = selectedId;
}

function renderStyleTimeline(root, timeline) {
  root.replaceChildren();
  root.dataset.totalBeats = String(timeline.total_beats);
  root.dataset.styleId = timeline.style_id;

  const ruler = document.createElement("div");
  ruler.className = "timeline-ruler";
  const rulerLabel = document.createElement("span");
  rulerLabel.textContent = "Role / instrument";
  const measures = document.createElement("div");
  measures.className = "timeline-measures";
  measures.style.setProperty("--phrase-bars", timeline.phrase_bars);
  for (let bar = 0; bar < timeline.phrase_bars; bar += 1) {
    const measure = document.createElement("span");
    measure.textContent = `M${bar + 1}`;
    measure.title = `Measure ${bar + 1} · ${timeline.bar_dynamics[bar]}% phrase energy`;
    const energy = document.createElement("i");
    energy.style.setProperty("--bar-energy", `${timeline.bar_dynamics[bar]}%`);
    measure.append(energy);
    measures.append(measure);
  }
  ruler.append(rulerLabel, measures);
  root.append(ruler);

  for (const lane of timeline.lanes) {
    const row = document.createElement("div");
    row.className = `timeline-lane lane-${lane.id}`;
    const label = document.createElement("div");
    label.className = "timeline-lane-label";
    const role = document.createElement("strong");
    role.textContent = lane.label;
    const instrument = document.createElement("span");
    instrument.textContent = lane.instrument;
    const level = document.createElement("small");
    level.textContent = `${lane.level}%`;
    label.append(role, instrument, level);

    const track = document.createElement("div");
    track.className = "timeline-track";
    track.style.setProperty("--phrase-bars", timeline.phrase_bars);
    track.style.setProperty("--lane-opacity", String(0.18 + (lane.level * 0.007)));
    track.style.setProperty("--lane-soft-opacity", String(0.1 + (lane.level * 0.005)));
    for (const event of lane.events) {
      const block = document.createElement("i");
      block.className = `timeline-event event-${event.kind}`;
      block.style.left = `${100 * event.start / timeline.total_beats}%`;
      block.style.width = `${Math.max(0.55, 100 * event.duration / timeline.total_beats)}%`;
      block.style.height = `${Math.max(18, Math.min(100, event.intensity))}%`;
      block.title = `${lane.label}: beat ${event.start + 1} · ${event.kind}`;
      track.append(block);
    }
    const playhead = document.createElement("b");
    playhead.className = "timeline-playhead";
    playhead.setAttribute("aria-hidden", "true");
    track.append(playhead);
    row.append(label, track);
    root.append(row);
  }
}

async function ensureLiveStyleTimeline(styleId, section = "variation_1") {
  const key = `${styleId}:${section}`;
  if (!styleId || liveTimelineStyleId === key) return;
  liveTimelineStyleId = key;
  try {
    let timeline = styleTimelineCache.get(key);
    if (!timeline) {
      timeline = await api(`/api/styles/${encodeURIComponent(styleId)}/timeline?section=${encodeURIComponent(section)}`);
      styleTimelineCache.set(key, timeline);
    }
    if (liveTimelineStyleId !== key) return;
    renderStyleTimeline(liveStyleTimeline, timeline);
    $("#live-timeline-state").textContent = `${timeline.phrase_bars} measures · live playhead`;
  } catch (error) {
    if (liveTimelineStyleId !== key) return;
    liveTimelineStyleId = null;
    $("#live-timeline-state").textContent = `Timeline unavailable: ${error.message}`;
  }
}

function updateTimelinePlayhead(root, status, elapsedMilliseconds) {
  const totalBeats = Number(root.dataset.totalBeats);
  if (!totalBeats || !status) return;
  const running = status.running && status.section !== "stopped";
  const originTicks = root === liveStyleTimeline ? (status.style_controls?.pattern_origin_ticks ?? 0) : 0;
  const projectedTicks = status.position_ticks - originTicks
    + (running ? elapsedMilliseconds * status.tempo_bpm * 96 / 60000 : 0);
  const progress = running ? ((projectedTicks / 96) % totalBeats) / totalBeats : 0;
  root.classList.toggle("playing", running);
  for (const playhead of root.querySelectorAll(".timeline-playhead")) {
    playhead.style.left = `${progress * 100}%`;
  }
}

function ensureBeatLights(beatsPerBar) {
  if (beatLights.children.length === beatsPerBar) return;
  beatLights.replaceChildren(...Array.from({ length: beatsPerBar }, (_, index) => {
    const light = document.createElement("li");
    light.className = "beat-light";
    light.dataset.beat = String(index);
    light.innerHTML = `<i aria-hidden="true"></i><span>${index + 1}</span>`;
    return light;
  }));
}

function renderBeatIndicator(status, elapsedMilliseconds) {
  ensureBeatLights(status.beats_per_bar);
  const activeBeat = projectedBeatIndex(status, elapsedMilliseconds);
  for (const light of beatLights.children) {
    const active = Number(light.dataset.beat) === activeBeat;
    light.classList.toggle("active", active);
    light.classList.toggle("downbeat", active && activeBeat === 0);
    if (active) light.setAttribute("aria-current", "step");
    else light.removeAttribute("aria-current");
  }
  beatLights.classList.toggle("running", activeBeat != null);
  beatLights.setAttribute(
    "aria-label",
    activeBeat == null
      ? `${status.beats_per_bar}/4 bar position, stopped`
      : `Beat ${activeBeat + 1} of ${status.beats_per_bar}`,
  );
  beatLabel.textContent = activeBeat == null
    ? `Ready · ${status.beats_per_bar}/4`
    : `Beat ${activeBeat + 1} / ${status.beats_per_bar}`;
}

function animateBeatIndicator(nowMilliseconds) {
  if (beatClock) {
    const elapsed = nowMilliseconds - beatClock.sampledAtMilliseconds;
    renderBeatIndicator(
      beatClock.status,
      elapsed,
    );
    updateTimelinePlayhead(liveStyleTimeline, beatClock.status, elapsed);
    if (styleDesignerDialog.open && designerPreviewing) {
      updateTimelinePlayhead(designerStyleTimeline, beatClock.status, elapsed);
    }
  }
  requestAnimationFrame(animateBeatIndicator);
}

function updateTempoKnob(value) {
  const minimum = Number(fixedTempo.min);
  const maximum = Number(fixedTempo.max);
  const bounded = Math.min(maximum, Math.max(minimum, value));
  const angle = -135 + (270 * (bounded - minimum) / (maximum - minimum));
  $("#tempo-knob").style.setProperty("--tempo-angle", `${angle}deg`);
  $("#arranger-fixed-tempo-value").textContent = bounded;
}

async function openAudioOutput() {
  try {
    const status = await api("/api/audio/outputs");
    const select = $("#audio-output-select");
    select.replaceChildren(new Option("No output selected", ""));
    for (const device of status.devices) {
      select.append(new Option(`${device.name} — ${device.id}`, device.id));
    }
    if (status.selected
        && [...select.options].some((option) => option.value === status.selected)) {
      select.value = status.selected;
    }
    setAudioOutputMessage(
      status.available
        ? "Saved output is available. Play the test chord or choose another output."
        : "Choose an output and play the test chord before saving.",
    );
    if (!audioOutputDialog.open) audioOutputDialog.showModal();
  } catch (error) {
    setArrangerMessage(`Could not load audio outputs: ${error.message}`, true);
  }
}

function setAudioOutputMessage(message, error = false) {
  const element = $("#audio-output-message");
  element.textContent = message;
  element.classList.toggle("error", error);
}

async function testAudioOutput() {
  const device = $("#audio-output-select").value;
  if (!device) return setAudioOutputMessage("Choose an output first.", true);
  try {
    setAudioOutputMessage("Playing a short C-major test chord…");
    await api("/api/audio/test", {
      method: "POST",
      body: JSON.stringify({ device }),
    });
    setAudioOutputMessage("Test played. If you heard it from the mixer, save this output.");
  } catch (error) {
    setAudioOutputMessage(error.message, true);
  }
}

async function saveAudioOutput() {
  const device = $("#audio-output-select").value;
  if (!device) return setAudioOutputMessage("Choose an output first.", true);
  try {
    await api("/api/audio/output", {
      method: "PUT",
      body: JSON.stringify({ device }),
    });
    audioOutputDialog.close();
    await loadArrangerStatus();
    setArrangerMessage("Analog accompaniment output saved. The arranger is ready.");
  } catch (error) {
    setAudioOutputMessage(error.message, true);
  }
}

function setStyleDesignerMessage(message, error = false) {
  const element = $("#style-designer-message");
  element.textContent = message;
  element.classList.toggle("error", error);
}

function cloneStyle(value) {
  return JSON.parse(JSON.stringify(value));
}

function populateDesignerOptions(catalog) {
  designerStyleSelect.replaceChildren(new Option("Create a new style", ""));
  for (const style of catalog.styles) {
    designerStyleSelect.append(new Option(style.name, style.id));
  }
  $("#designer-meter").replaceChildren(...catalog.meters.map((meter) => (
    new Option(`${meter}/4`, meter)
  )));
  for (const card of document.querySelectorAll(".designer-layer")) {
    const select = card.querySelector('[data-field="instrument"]');
    const groups = new Map();
    for (const instrument of catalog.instruments) {
      if (!groups.has(instrument.category)) {
        groups.set(instrument.category, document.createElement("optgroup"));
        groups.get(instrument.category).label = instrument.category;
      }
      groups.get(instrument.category).append(new Option(instrument.name, instrument.id));
    }
    select.replaceChildren(...groups.values());
  }
}

function populateDesignerTemplates(meter, selectedId = "") {
  const templates = styleDesignerCatalog?.templates.filter(
    (template) => template.beats_per_bar === Number(meter),
  ) ?? [];
  const select = $("#designer-template");
  select.replaceChildren(...templates.map((template) => (
    new Option(template.name, template.id)
  )));
  if (templates.some((template) => template.id === selectedId)) {
    select.value = selectedId;
  }
  return templates;
}

function resetDesignerDelete() {
  designerDeleteArmed = false;
  $("#designer-delete").textContent = "Delete style";
}

function renderDesignerPreviewState(status) {
  designerPreviewing = Boolean(status?.style_previewing);
  const preview = $(".designer-preview");
  preview.classList.toggle("playing", designerPreviewing);
  $("#designer-preview-play").textContent = designerPreviewing ? "Restart" : "Preview";
  $("#designer-preview-play").setAttribute("aria-pressed", String(designerPreviewing));
  $("#designer-preview-play").disabled = !status?.output_configured;
  $("#designer-preview-stop").disabled = !designerPreviewing;
  if (designerPreviewing && status.preview_tempo_bpm != null) {
    const tempo = $("#designer-preview-tempo");
    if (document.activeElement !== tempo) {
      tempo.value = status.preview_tempo_bpm;
      $("#designer-preview-tempo-value").textContent = status.preview_tempo_bpm;
    }
  }
}

function renderDesignerStyle(style, identifier = "") {
  const value = cloneStyle(style);
  designerStyleSelect.value = identifier;
  $("#designer-name").value = value.name;
  $("#designer-meter").value = value.beats_per_bar;
  populateDesignerTemplates(value.beats_per_bar, value.base_style_id);
  $("#designer-phrase-bars").value = value.phrase_bars;
  $("#designer-tempo").value = value.tempo_bpm;
  $("#designer-tempo-value").textContent = value.tempo_bpm;
  $("#designer-preview-tempo").value = value.tempo_bpm;
  $("#designer-preview-tempo-value").textContent = value.tempo_bpm;
  for (const layerName of ["bass", "comp", "fill", "backing"]) {
    const card = document.querySelector(`.designer-layer[data-layer="${layerName}"]`);
    card.querySelector('[data-field="instrument"]').value = value[layerName].instrument;
    card.querySelector('[data-field="volume"]').value = value[layerName].volume;
    card.querySelector('[data-field="volume-output"]').textContent = value[layerName].volume;
    card.querySelector('[data-field="octave"]').value = value[layerName].octave;
    card.querySelector('[data-field="gate"]').value = value[layerName].gate_percent;
    card.querySelector('[data-field="gate-output"]').textContent = value[layerName].gate_percent;
  }
  $("#designer-drums-enabled").checked = value.drums_enabled;
  $("#designer-drums-volume").value = value.drums_volume;
  $("#designer-drums-volume-value").textContent = value.drums_volume;
  $("#designer-drums-volume").disabled = !value.drums_enabled;
  const editing = Boolean(identifier);
  $("#designer-delete").hidden = !editing;
  $("#designer-save").textContent = editing ? "Update style" : "Save new style";
  resetDesignerDelete();
  renderDesignerTimeline();
}

function renderDesignerTimeline() {
  const template = styleDesignerCatalog?.templates.find(
    (item) => item.id === $("#designer-template").value,
  );
  if (!template?.timeline) return;
  const timeline = cloneStyle(template.timeline);
  const phraseBars = Number($("#designer-phrase-bars").value);
  timeline.style_id = "designer-preview";
  timeline.name = $("#designer-name").value.trim() || "Unsaved style";
  timeline.phrase_bars = phraseBars;
  timeline.total_beats = phraseBars * timeline.beats_per_bar;
  timeline.bar_dynamics = timeline.bar_dynamics.slice(0, phraseBars);
  for (const lane of timeline.lanes) {
    let level;
    let instrumentName;
    let gate = 1;
    if (lane.id === "drums") {
      const enabled = $("#designer-drums-enabled").checked;
      level = enabled ? Number($("#designer-drums-volume").value) : 0;
      instrumentName = enabled ? "Studio drum kit" : "Off";
    } else {
      const card = document.querySelector(`.designer-layer[data-layer="${lane.id}"]`);
      const instrumentId = card.querySelector('[data-field="instrument"]').value;
      const instrument = styleDesignerCatalog.instruments.find(
        (item) => item.id === instrumentId,
      );
      level = instrumentId === "none"
        ? 0
        : Number(card.querySelector('[data-field="volume"]').value);
      instrumentName = instrument?.name ?? instrumentId;
      gate = Number(card.querySelector('[data-field="gate"]').value) / 100;
    }
    lane.level = level;
    lane.instrument = instrumentName;
    lane.events = lane.events
      .filter((event) => event.start < timeline.total_beats)
      .map((event) => ({ ...event, duration: event.duration * gate }));
  }
  renderStyleTimeline(designerStyleTimeline, timeline);
  if (designerPreviewing && beatClock) {
    updateTimelinePlayhead(designerStyleTimeline, beatClock.status, 0);
  }
}

function newDesignerStyle() {
  if (!styleDesignerCatalog) return;
  renderDesignerStyle(styleDesignerCatalog.defaults);
  setStyleDesignerMessage("New style ready. Choose a template and shape your ensemble.");
}

function selectedDesignerStyle() {
  return styleDesignerCatalog?.styles.find((style) => style.id === designerStyleSelect.value);
}

async function openStyleDesigner() {
  try {
    styleDesignerCatalog = await api("/api/styles");
    populateDesignerOptions(styleDesignerCatalog);
    const selected = styleDesignerCatalog.styles.find(
      (style) => style.id === arrangerStatus?.style,
    );
    if (selected) renderDesignerStyle(selected, selected.id);
    else newDesignerStyle();
    renderDesignerPreviewState(arrangerStatus);
    if (!arrangerStatus?.output_configured) {
      setStyleDesignerMessage(
        "Choose an accompaniment audio output before using Preview.",
        true,
      );
    }
    if (!styleDesignerDialog.open) styleDesignerDialog.showModal();
  } catch (error) {
    setArrangerMessage(`Could not load the style designer: ${error.message}`, true);
  }
}

function collectDesignerStyle() {
  const value = {
    schema_version: 2,
    name: $("#designer-name").value.trim(),
    base_style_id: $("#designer-template").value,
    beats_per_bar: Number($("#designer-meter").value),
    phrase_bars: Number($("#designer-phrase-bars").value),
    tempo_bpm: Number($("#designer-tempo").value),
    drums_enabled: $("#designer-drums-enabled").checked,
    drums_volume: Number($("#designer-drums-volume").value),
  };
  for (const layerName of ["bass", "comp", "fill", "backing"]) {
    const card = document.querySelector(`.designer-layer[data-layer="${layerName}"]`);
    value[layerName] = {
      instrument: card.querySelector('[data-field="instrument"]').value,
      volume: Number(card.querySelector('[data-field="volume"]').value),
      octave: Number(card.querySelector('[data-field="octave"]').value),
      gate_percent: Number(card.querySelector('[data-field="gate"]').value),
    };
  }
  return value;
}

async function saveDesignerStyle(event) {
  event.preventDefault();
  const identifier = designerStyleSelect.value;
  try {
    await stopDesignerPreview(true);
    setStyleDesignerMessage(identifier ? "Updating style…" : "Saving new style…");
    const saved = await api(identifier ? `/api/styles/${identifier}` : "/api/styles", {
      method: identifier ? "PUT" : "POST",
      body: JSON.stringify(collectDesignerStyle()),
    });
    styleDesignerCatalog = await api("/api/styles");
    populateDesignerOptions(styleDesignerCatalog);
    renderDesignerStyle(saved, saved.id);
    styleTimelineCache.delete(saved.id);
    liveTimelineStyleId = null;
    await loadArrangerStatus();
    if (arrangerStatus?.style !== saved.id) await arrangerCommand("style", saved.id);
    setStyleDesignerMessage(`Saved “${saved.name}”. It is now the selected arranger style.`);
  } catch (error) {
    setStyleDesignerMessage(error.message, true);
  }
}

async function deleteDesignerStyle() {
  const style = selectedDesignerStyle();
  if (!style) return;
  if (!designerDeleteArmed) {
    designerDeleteArmed = true;
    $("#designer-delete").textContent = "Confirm delete";
    setStyleDesignerMessage(`Press Confirm delete to remove “${style.name}”.`);
    return;
  }
  try {
    await stopDesignerPreview(true);
    await api(`/api/styles/${style.id}`, { method: "DELETE" });
    styleTimelineCache.delete(style.id);
    if (liveTimelineStyleId === style.id) liveTimelineStyleId = null;
    styleDesignerCatalog = await api("/api/styles");
    populateDesignerOptions(styleDesignerCatalog);
    newDesignerStyle();
    await loadArrangerStatus();
    setStyleDesignerMessage(`Deleted “${style.name}”.`);
  } catch (error) {
    setStyleDesignerMessage(error.message, true);
  }
}

async function startDesignerPreview() {
  clearTimeout(designerPreviewRestartTimer);
  designerPreviewRestartTimer = null;
  try {
    const tempo = Number($("#designer-preview-tempo").value);
    setStyleDesignerMessage(`Starting unsaved preview at ${tempo} BPM…`);
    const status = await api("/api/styles/preview", {
      method: "POST",
      body: JSON.stringify({ style: collectDesignerStyle(), tempo_bpm: tempo }),
    });
    renderDesignerPreviewState(status);
    setStyleDesignerMessage(
      `Previewing the unsaved style at ${tempo} BPM in C major. It stops automatically after 30 seconds.`,
    );
  } catch (error) {
    renderDesignerPreviewState(arrangerStatus);
    setStyleDesignerMessage(error.message, true);
  }
}

async function stopDesignerPreview(quiet = false) {
  clearTimeout(designerPreviewRestartTimer);
  designerPreviewRestartTimer = null;
  if (!designerPreviewing && !arrangerStatus?.style_previewing) return;
  try {
    const status = await api("/api/styles/preview", { method: "DELETE" });
    arrangerStatus = status;
    renderDesignerPreviewState(status);
    if (!quiet) setStyleDesignerMessage("Preview stopped. The live arranger is restored.");
  } catch (error) {
    if (!quiet) setStyleDesignerMessage(error.message, true);
  }
}

function scheduleDesignerPreviewRestart(target, delay = DESIGNER_PREVIEW_RESTART_DELAY_MS) {
  if (!designerPreviewing || DESIGNER_NON_AUDIO_FIELDS.has(target.id)) return;
  clearTimeout(designerPreviewRestartTimer);
  setStyleDesignerMessage("Updating the live preview…");
  designerPreviewRestartTimer = setTimeout(() => {
    designerPreviewRestartTimer = null;
    if (designerPreviewing && styleDesignerDialog.open) startDesignerPreview();
  }, delay);
}

async function closeStyleDesigner() {
  await stopDesignerPreview(true);
  styleDesignerDialog.close();
}

function styleName(styleId) {
  return arrangerStatus?.styles.find((style) => style.id === styleId)?.name ?? styleId;
}

function setArrangerMessage(message, error = false) {
  arrangerMessage.textContent = message;
  arrangerMessage.classList.toggle("error", error);
}

async function loadProfile() {
  try {
    midiProfile = await api("/api/midi/profile");
    if (midiProfile) {
      applyProfileToSurface(midiProfile);
      performanceControlBindings = bindingsFromProfile(midiProfile);
    }
  } catch (error) {
    showMessage(`Could not load the saved MIDI profile: ${error.message}`, true);
  } finally {
    profileLoaded = true;
    updateConnectionSummary();
    restoreSavedPorts();
    maybeShowFirstRunWizard();
  }
}

function applyProfileToSurface(profile) {
  accordion.configureMidi(profile);
}

function restoreSavedPorts() {
  if (!profileLoaded || !midiProfile || !portStatus || profileRestoreAttempted) return;
  const inputAvailable = portStatus.inputs.includes(midiProfile.input_port);
  const outputAvailable = midiProfile.output_port == null
    || portStatus.outputs.includes(midiProfile.output_port);
  if (portStatus.selected_input === midiProfile.input_port
      && portStatus.selected_output === midiProfile.output_port) {
    profileRestoreAttempted = true;
    return;
  }
  if (!inputAvailable) return;
  const desiredOutput = outputAvailable ? midiProfile.output_port : null;
  if (portStatus.selected_input === midiProfile.input_port
      && portStatus.selected_output === desiredOutput) {
    profileRestoreAttempted = outputAvailable;
    return;
  }
  profileRestoreAttempted = outputAvailable;
  send({
    type: "ports.select",
    input: midiProfile.input_port,
    output: desiredOutput,
  });
}

function maybeShowFirstRunWizard() {
  if (!profileLoaded || !portStatus || midiProfile || firstRunWizardShown) return;
  firstRunWizardShown = true;
  openWizard();
}

function updateConnectionSummary() {
  $("#profile-input").textContent = midiProfile?.input_port ?? "Not configured";
  $("#profile-output").textContent = midiProfile?.output_port ?? "Not configured";
  if (midiProfile) {
    const roles = ROLE_ORDER.map((role) => `${role} ch ${midiProfile.roles[role].primary_channel}`);
    $("#profile-roles").textContent = roles.join(" · ");
  } else {
    $("#profile-roles").textContent = "Run setup to detect channels";
  }
  const controlCount = midiProfile?.performance_controls?.bindings?.length ?? 0;
  $("#profile-controls").textContent = controlCount
    ? `${controlCount} of ${PERFORMANCE_CONTROL_ACTIONS.length} learned`
    : "No controls learned";
  $("#open-performance-controls").disabled = !midiProfile;

  if (portStatus?.error) {
    showMessage(portStatus.error, true);
    return;
  }
  if (!midiProfile) {
    showMessage("No MIDI profile is saved yet.");
    return;
  }
  if (!portStatus?.inputs.includes(midiProfile.input_port)) {
    showMessage(`Saved input is unavailable: ${midiProfile.input_port}. Reconnect it or run setup again.`, true);
    return;
  }
  const input = portStatus.input_connected ? "input connected" : "input waiting";
  const output = midiProfile.output_port == null
    ? "no simulator output configured"
    : (portStatus.output_connected ? "output connected" : "output waiting");
  showMessage(`${input}; ${output}. Saved profile restored by exact port name.`);
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
  send({
    type: "midi.send",
    bytes: [status, note, active ? SIMULATOR_VELOCITY : 0],
  });
}

function freshCaptures() {
  return { treble: [], bass: [], chord: [] };
}

function openWizard() {
  profileRestoreAttempted = false;
  showWizardStep(1);
  if (midiProfile) {
    inputSelect.value = midiProfile.input_port;
    outputSelect.value = midiProfile.output_port ?? "";
  }
  if (!wizard.open) wizard.showModal();
}

function showWizardStep(step) {
  wizardStep = step;
  for (const section of wizard.querySelectorAll(".wizard-step")) {
    section.hidden = Number(section.dataset.step) !== step;
  }
  for (const item of wizard.querySelectorAll("[data-progress]")) {
    const progress = Number(item.dataset.progress);
    item.classList.toggle("current", progress === step);
    item.classList.toggle("complete", progress < step);
  }
}

async function connectForDetection() {
  if (!inputSelect.value) {
    setWizardMessage("port", "Select the accordion input before continuing.", true);
    return;
  }
  try {
    const status = await api("/api/midi/ports", {
      method: "PUT",
      body: JSON.stringify({
        input: inputSelect.value,
        output: outputSelect.value || null,
      }),
    });
    portStatus = status;
    if (!status.input_connected) throw new Error("The selected MIDI input did not open.");
    captures = freshCaptures();
    detection = null;
    captureIndex = 0;
    capturing = false;
    updateCaptureCard();
    setWizardMessage("detect", "Start capture when you are ready to play only the requested part.");
    showWizardStep(2);
  } catch (error) {
    setWizardMessage("port", error.message, true);
  }
}

function setWizardMessage(area, message, error = false) {
  const element = $(`#wizard-${area}-message`);
  element.textContent = message;
  element.classList.toggle("error", error);
}

function updateCaptureCard() {
  const role = ROLE_ORDER[captureIndex];
  const copy = ROLE_COPY[role];
  const observations = captures[role];
  const channels = [...new Set(observations.map((item) => item.channel))].sort((a, b) => a - b);
  $("#capture-kicker").textContent = copy.kicker;
  $("#capture-title").textContent = copy.title;
  $("#capture-instructions").textContent = copy.instructions;
  $("#capture-count").textContent = `${observations.length} note event${observations.length === 1 ? "" : "s"}`;
  $("#capture-channels").textContent = channels.length
    ? `Observed ${channels.map((channel) => `ch ${channel}`).join(", ")}`
    : "No channels observed";
  $("#toggle-capture").textContent = capturing ? "Stop capture" : `Start ${role} capture`;
  $("#toggle-capture").classList.toggle("active", capturing);
  $("#capture-card").classList.toggle("recording", capturing);
  $("#next-capture").textContent = copy.next;
  $("#next-capture").disabled = capturing || observations.length === 0;
}

function toggleCapture() {
  capturing = !capturing;
  updateCaptureCard();
  const role = ROLE_ORDER[captureIndex];
  setWizardMessage(
    "detect",
    capturing
      ? `Listening for ${role} note-on events…`
      : `${captures[role].length} ${role} note events captured. Continue or capture more.`,
  );
}

function captureIncomingNote(event) {
  if (!capturing || wizardStep !== 2 || event.direction !== "in") return;
  if (event.message_type !== "note_on" || event.velocity <= 0) return;
  if (event.channel == null || event.note == null) return;
  const role = ROLE_ORDER[captureIndex];
  captures[role].push({ channel: event.channel, note: event.note });
  $("#capture-pulse").classList.remove("hit");
  requestAnimationFrame(() => $("#capture-pulse").classList.add("hit"));
  updateCaptureCard();
}

async function advanceCapture() {
  if (capturing || captures[ROLE_ORDER[captureIndex]].length === 0) return;
  if (captureIndex < ROLE_ORDER.length - 1) {
    captureIndex += 1;
    updateCaptureCard();
    setWizardMessage("detect", "Start capture when you are ready to play only the requested part.");
    return;
  }
  try {
    setWizardMessage("detect", "Comparing observed channel activity…");
    const result = await api("/api/midi/detect", {
      method: "POST",
      body: JSON.stringify(captures),
    });
    detection = result.roles;
    renderDetectionReview();
    showWizardStep(3);
  } catch (error) {
    setWizardMessage("detect", `Detection failed: ${error.message}`, true);
  }
}

function renderDetectionReview() {
  const review = $("#detection-review");
  review.replaceChildren();
  for (const role of ROLE_ORDER) {
    const result = detection[role];
    const card = document.createElement("article");
    card.className = "detection-card";
    const heading = document.createElement("div");
    heading.innerHTML = `<span>${role}</span><strong>${Math.round(result.confidence * 100)}% confidence</strong>`;
    const label = document.createElement("label");
    label.innerHTML = "<span>Observed channel</span>";
    const select = document.createElement("select");
    select.dataset.role = role;
    for (const candidate of result.candidates) {
      const range = `${Math.min(...candidate.notes)}–${Math.max(...candidate.notes)}`;
      select.append(new Option(
        `Channel ${candidate.channel} · ${candidate.event_count} events · notes ${range}`,
        String(candidate.channel),
      ));
    }
    select.value = String(result.primary_channel);
    select.addEventListener("change", () => chooseCandidate(role, Number(select.value), card));
    label.append(select);
    const details = document.createElement("p");
    details.className = "detection-details";
    card.append(heading, label, details);
    review.append(card);
    updateDetectionCard(role, card);
  }
}

function chooseCandidate(role, channel, card) {
  const result = detection[role];
  const candidate = result.candidates.find((item) => item.channel === channel);
  result.primary_channel = candidate.channel;
  result.note_min = Math.min(...candidate.notes);
  result.note_max = Math.max(...candidate.notes);
  result.event_count = candidate.event_count;
  result.confidence = candidate.confidence;
  updateDetectionCard(role, card);
}

function updateDetectionCard(role, card) {
  const result = detection[role];
  card.querySelector("strong").textContent = `${Math.round(result.confidence * 100)}% confidence`;
  card.querySelector(".detection-details").textContent =
    `Selected channel ${result.primary_channel}; observed notes ${result.note_min}–${result.note_max} across ${result.event_count} events.`;
  card.classList.toggle("ambiguous", result.confidence < 0.75);
}

async function saveMidiProfile() {
  const preservedControls = midiProfile?.input_port === inputSelect.value
    ? midiProfile.performance_controls
    : { bindings: [] };
  const profile = {
    schema_version: 1,
    detection_method: "guided-activity-v1",
    input_port: inputSelect.value,
    output_port: outputSelect.value || null,
    roles: detection,
    performance_controls: preservedControls,
  };
  try {
    setWizardMessage("save", "Saving the reviewed profile…");
    midiProfile = await api("/api/midi/profile", {
      method: "PUT",
      body: JSON.stringify(profile),
    });
    profileRestoreAttempted = true;
    performanceControlBindings = bindingsFromProfile(midiProfile);
    applyProfileToSurface(midiProfile);
    updateConnectionSummary();
    wizard.close();
    showMessage("MIDI profile saved. The detected treble mapping is active.");
  } catch (error) {
    setWizardMessage("save", `Could not save the profile: ${error.message}`, true);
  }
}

function setPerformanceControlMessage(message, error = false) {
  const element = $("#performance-control-message");
  element.textContent = message;
  element.classList.toggle("error", error);
}

function renderPerformanceControls() {
  const list = $("#performance-control-list");
  list.replaceChildren();
  for (const { action, label } of PERFORMANCE_CONTROL_ACTIONS) {
    const messages = performanceControlBindings.get(action);
    const row = document.createElement("article");
    row.className = "performance-control-row";
    row.classList.toggle("learning", learningControlAction === action);
    row.dataset.action = action;

    const title = document.createElement("strong");
    title.textContent = label;
    const fingerprint = document.createElement("code");
    fingerprint.className = "performance-control-fingerprint";
    fingerprint.textContent = learningControlAction === action
      ? (learnedControlMessages.length
        ? formatMessageSequence(learnedControlMessages)
        : "Listening for one switch press…")
      : formatMessageSequence(messages);

    const clear = document.createElement("button");
    clear.className = "secondary-button";
    clear.type = "button";
    clear.textContent = "Clear";
    clear.disabled = !messages || learningControlAction !== null;
    clear.addEventListener("click", () => {
      performanceControlBindings.delete(action);
      renderPerformanceControls();
      setPerformanceControlMessage(`${label} cleared locally. Save controls to apply the change.`);
    });

    const learn = document.createElement("button");
    learn.className = "secondary-button";
    learn.type = "button";
    learn.textContent = learningControlAction === action ? "Listening…" : "Learn";
    learn.disabled = learningControlAction !== null;
    learn.addEventListener("click", () => startPerformanceLearning(action, label));
    row.append(title, fingerprint, clear, learn);
    list.append(row);
  }
  $("#cancel-performance-learning").hidden = learningControlAction === null;
  $("#save-performance-controls").disabled = learningControlAction !== null;
}

function openPerformanceControls() {
  if (!midiProfile) {
    showMessage("Save a MIDI profile before learning performance controls.", true);
    return;
  }
  if (!portStatus?.input_connected || portStatus.selected_input !== midiProfile.input_port) {
    showMessage("Connect the exact saved accordion input before learning controls.", true);
    return;
  }
  performanceControlBindings = bindingsFromProfile(midiProfile);
  learningControlAction = null;
  learnedControlMessages = [];
  renderPerformanceControls();
  setPerformanceControlMessage("Choose Learn, then press the corresponding accordion switch once.");
  if (!performanceControlDialog.open) performanceControlDialog.showModal();
}

function startPerformanceLearning(action, label) {
  if (learningControlAction !== null) return;
  if (!send({ type: "performance_controls.capture", active: true })) return;
  learningControlAction = action;
  learnedControlMessages = [];
  renderPerformanceControls();
  setPerformanceControlMessage(`Listening for ${label}. Press that accordion switch once.`);
}

function capturePerformanceControl(event) {
  if (learningControlAction === null || !isLearnableControlEvent(event)) return;
  learnedControlMessages.push([...event.bytes]);
  clearTimeout(controlQuietTimer);
  controlQuietTimer = setTimeout(finishPerformanceLearning, CONTROL_CAPTURE_QUIET_MS);
  if (learnedControlMessages.length === 1) {
    controlMaximumTimer = setTimeout(finishPerformanceLearning, CONTROL_CAPTURE_MAXIMUM_MS);
  }
  renderPerformanceControls();
  if (learnedControlMessages.length >= CONTROL_CAPTURE_MAX_MESSAGES) finishPerformanceLearning();
}

function clearPerformanceLearningTimers() {
  clearTimeout(controlQuietTimer);
  clearTimeout(controlMaximumTimer);
  controlQuietTimer = null;
  controlMaximumTimer = null;
}

function finishPerformanceLearning() {
  if (learningControlAction === null || learnedControlMessages.length === 0) return;
  const action = learningControlAction;
  const label = PERFORMANCE_CONTROL_ACTIONS.find((item) => item.action === action)?.label ?? action;
  performanceControlBindings.set(action, learnedControlMessages.map((message) => [...message]));
  clearPerformanceLearningTimers();
  learningControlAction = null;
  learnedControlMessages = [];
  send({ type: "performance_controls.capture", active: false });
  renderPerformanceControls();
  setPerformanceControlMessage(`${label} learned locally. Save controls to activate it.`);
}

function cancelPerformanceLearning(notifyServer = true) {
  if (learningControlAction === null) return;
  clearPerformanceLearningTimers();
  learningControlAction = null;
  learnedControlMessages = [];
  if (notifyServer) send({ type: "performance_controls.capture", active: false });
  renderPerformanceControls();
  setPerformanceControlMessage("Learning cancelled. Existing saved controls are unchanged.");
}

async function savePerformanceControls() {
  if (!midiProfile || learningControlAction !== null) return;
  try {
    setPerformanceControlMessage("Saving learned controls…");
    midiProfile = await api("/api/midi/performance-controls", {
      method: "PUT",
      body: JSON.stringify({ bindings: orderedBindings(performanceControlBindings) }),
    });
    performanceControlBindings = bindingsFromProfile(midiProfile);
    updateConnectionSummary();
    performanceControlDialog.close();
    showMessage("Performance controls saved. Learned accordion switches now control the arranger.");
  } catch (error) {
    setPerformanceControlMessage(`Could not save controls: ${error.message}`, true);
  }
}

$("#open-midi-wizard").addEventListener("click", openWizard);
$("#open-performance-controls").addEventListener("click", openPerformanceControls);
$("#refresh-ports").addEventListener("click", () => send({ type: "status.request" }));
$("#connect-and-detect").addEventListener("click", connectForDetection);
$("#back-to-ports").addEventListener("click", () => {
  capturing = false;
  showWizardStep(1);
});
$("#toggle-capture").addEventListener("click", toggleCapture);
$("#next-capture").addEventListener("click", advanceCapture);
$("#repeat-detection").addEventListener("click", () => {
  captures = freshCaptures();
  detection = null;
  captureIndex = 0;
  capturing = false;
  updateCaptureCard();
  showWizardStep(2);
});
$("#save-midi-profile").addEventListener("click", saveMidiProfile);
$("#cancel-performance-learning").addEventListener("click", () => cancelPerformanceLearning());
$("#save-performance-controls").addEventListener("click", savePerformanceControls);
$("#close-performance-controls").addEventListener("click", () => {
  cancelPerformanceLearning();
  performanceControlDialog.close();
});
performanceControlDialog.addEventListener("close", () => cancelPerformanceLearning());
wizard.addEventListener("close", () => {
  capturing = false;
  updateCaptureCard();
});

accordion.addEventListener("surface-note", ({ detail }) => {
  if (detail.channel == null || detail.note == null) {
    if (detail.active) showMessage("Run MIDI setup before using the simulator.", true);
    return;
  }
  sendNote(detail.channel, detail.note, detail.active);
});

accordion.addEventListener("surface-left", ({ detail }) => {
  for (const note of detail.notes) {
    sendNote(detail.channel, note, detail.active);
  }
});

accordion.addEventListener("unmapped-button", () => {
  showMessage("That visual button has no MIDI note observed by the setup wizard.", true);
});

arrangerStyleGroup.addEventListener("change", () => {
  browsingStyleGroup = arrangerStyleGroup.value;
  populateArrangerStyles(arrangerStatus?.styles ?? [], browsingStyleGroup);
});
arrangerStyle.addEventListener("change", () => arrangerCommand("style", arrangerStyle.value));
$("#open-style-designer").addEventListener("click", openStyleDesigner);
$("[data-close-style-designer]").addEventListener("click", closeStyleDesigner);
styleDesignerDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeStyleDesigner();
});
styleDesignerForm.addEventListener("submit", saveDesignerStyle);
designerStyleSelect.addEventListener("change", async () => {
  const wasPreviewing = designerPreviewing;
  await stopDesignerPreview(true);
  const style = selectedDesignerStyle();
  if (style) {
    renderDesignerStyle(style, style.id);
    setStyleDesignerMessage(`Editing “${style.name}”.`);
  } else {
    newDesignerStyle();
  }
  if (wasPreviewing) await startDesignerPreview();
});
$("#designer-new").addEventListener("click", async () => {
  const wasPreviewing = designerPreviewing;
  await stopDesignerPreview(true);
  newDesignerStyle();
  if (wasPreviewing) await startDesignerPreview();
});
$("#designer-delete").addEventListener("click", deleteDesignerStyle);
$("#designer-preview-play").addEventListener("click", startDesignerPreview);
$("#designer-preview-stop").addEventListener("click", () => stopDesignerPreview());
$("#designer-preview-tempo").addEventListener("input", ({ target }) => {
  $("#designer-preview-tempo-value").textContent = target.value;
});
$("#designer-preview-tempo").addEventListener("change", () => {
  if (designerPreviewing) startDesignerPreview();
});
$("#designer-meter").addEventListener("change", ({ target }) => {
  const templates = populateDesignerTemplates(target.value);
  const template = templates[0];
  if (!template) return;
  $("#designer-template").value = template.id;
  if (!designerStyleSelect.value) {
    $("#designer-tempo").value = template.tempo_bpm;
    $("#designer-tempo-value").textContent = template.tempo_bpm;
  }
});
$("#designer-template").addEventListener("change", ({ target }) => {
  const template = styleDesignerCatalog?.templates.find((item) => item.id === target.value);
  if (!template || designerStyleSelect.value) return;
  $("#designer-tempo").value = template.tempo_bpm;
  $("#designer-tempo-value").textContent = template.tempo_bpm;
});
$("#designer-tempo").addEventListener("input", ({ target }) => {
  $("#designer-tempo-value").textContent = target.value;
  if (!designerPreviewing) {
    $("#designer-preview-tempo").value = target.value;
    $("#designer-preview-tempo-value").textContent = target.value;
  }
});
for (const slider of document.querySelectorAll('.designer-layer [data-field="volume"]')) {
  slider.addEventListener("input", ({ target }) => {
    target.closest(".designer-layer").querySelector('[data-field="volume-output"]').textContent = target.value;
  });
}
for (const slider of document.querySelectorAll('.designer-layer [data-field="gate"]')) {
  slider.addEventListener("input", ({ target }) => {
    target.closest(".designer-layer").querySelector('[data-field="gate-output"]').textContent = target.value;
  });
}
$("#designer-drums-enabled").addEventListener("change", ({ target }) => {
  $("#designer-drums-volume").disabled = !target.checked;
});
$("#designer-drums-volume").addEventListener("input", ({ target }) => {
  $("#designer-drums-volume-value").textContent = target.value;
});
styleDesignerForm.addEventListener("change", ({ target }) => {
  renderDesignerTimeline();
  scheduleDesignerPreviewRestart(target, 40);
});
styleDesignerForm.addEventListener("input", ({ target }) => {
  renderDesignerTimeline();
  scheduleDesignerPreviewRestart(target);
});
$("#arranger-tempo-mode").addEventListener("click", () => {
  const mode = arrangerStatus?.tempo_mode === "fixed" ? "bass_auto" : "fixed";
  arrangerCommand("tempo_mode", mode);
});
fixedTempo.addEventListener("input", () => updateTempoKnob(Number(fixedTempo.value)));
fixedTempo.addEventListener("change", () => arrangerCommand("tempo", Number(fixedTempo.value)));
$("#open-audio-output").addEventListener("click", openAudioOutput);
$("#test-audio-output").addEventListener("click", testAudioOutput);
$("#save-audio-output").addEventListener("click", saveAudioOutput);
$("#arranger-intro").addEventListener("click", () => arrangerCommand("intro"));
$("#arranger-start").addEventListener("click", () => arrangerCommand("start"));
$("#arranger-stop").addEventListener("click", () => arrangerCommand("stop"));
$("#arranger-ending").addEventListener("click", () => arrangerCommand("ending"));
$("#arranger-fill-1").addEventListener("click", () => arrangerCommand("fill", 1));
$("#arranger-fill-2").addEventListener("click", () => arrangerCommand("fill", 2));
$("#arranger-sync").addEventListener("click", () => {
  arrangerCommand("sync", !arrangerStatus?.sync_enabled);
});

document.addEventListener("keydown", (event) => {
  if (event.repeat || wizard.open || audioOutputDialog.open || styleDesignerDialog.open) return;
  const target = event.target;
  if (target instanceof HTMLElement
      && (target.isContentEditable || ["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(target.tagName))) {
    return;
  }
  const commands = {
    KeyI: ["intro", null],
    Enter: ["start", null],
    Space: ["stop", null],
    KeyE: ["ending", null],
    Digit1: ["fill", 1],
    Digit2: ["fill", 2],
    KeyS: ["sync", !arrangerStatus?.sync_enabled],
  };
  const command = commands[event.code];
  if (!command) return;
  event.preventDefault();
  arrangerCommand(...command);
});

$("#clear-events").addEventListener("click", () => {
  eventList.innerHTML = '<li class="empty-event">No MIDI events received.</li>';
});

setInterval(() => {
  rateOutput.textContent = `${eventsThisSecond} msg/s`;
  eventsThisSecond = 0;
}, 1000);

setInterval(loadArrangerStatus, 350);
requestAnimationFrame(animateBeatIndicator);

loadProfile();
loadArrangerStatus();
connectSocket();


function renderImportedStyleControls(status) {
  const root = $("#imported-style-controls");
  const controls = status.style_controls;
  root.hidden = !controls;
  if (!controls) {
    $("#arranger-intro span").textContent = "Intro";
    $("#arranger-ending span").textContent = "Ending";
    return;
  }
  const signature = JSON.stringify([status.style, controls.available, controls.tracks.map(track => track.role)]);
  if (root.dataset.style !== signature) {
    root.dataset.style = signature;
    $("#style-variations").replaceChildren(...controls.available.variation.map(number => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = number;
      button.dataset.variation = number;
      button.setAttribute("aria-label", `Variation ${number}`);
      button.addEventListener("click", () => arrangerCommand("variation", number));
      return button;
    }));
    for (const kind of ["intro", "ending"]) {
      $(`#style-${kind}-choice`).replaceChildren(...controls.available[kind].map(number => new Option(`${kind === "intro" ? "Intro" : "Ending"} ${number}`, number)));
    }
    $("#style-track-mixer").replaceChildren(...controls.tracks.map(track => {
      const row = document.createElement("div");
      row.className = "style-mix-row";
      row.dataset.role = track.role;
      const label = document.createElement("span");
      label.textContent = track.name;
      row.append(label);
      for (const property of ["muted", "solo"]) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = property === "muted" ? "Mute" : "Solo";
        button.dataset.property = property;
        button.setAttribute("aria-label", `${button.textContent} ${track.name}`);
        button.addEventListener("click", () => arrangerCommand("track_mix", { role: track.role, [property]: button.getAttribute("aria-pressed") !== "true" }));
        row.append(button);
      }
      const volume = document.createElement("input");
      volume.type = "range"; volume.min = 0; volume.max = 100; volume.step = 1;
      volume.setAttribute("aria-label", `${track.name} volume`);
      volume.addEventListener("change", () => arrangerCommand("track_mix", { role: track.role, volume: Number(volume.value) }));
      row.append(volume);
      return row;
    }));
  }
  for (const button of $("#style-variations").children) button.setAttribute("aria-pressed", String(Number(button.dataset.variation) === controls.variation));
  for (const kind of ["intro", "ending"]) $(`#style-${kind}-choice`).value = controls[kind];
  $("#style-variation-state").textContent = controls.active_variation !== controls.variation ? `Variation ${controls.variation} after the fill or at the next bar` : `Variation ${controls.variation}`;
  $("#arranger-intro span").textContent = `Intro ${controls.intro}`;
  $("#arranger-ending span").textContent = `Ending ${controls.ending}`;
  for (const track of controls.tracks) {
    const row = $(`#style-track-mixer [data-role="${track.role}"]`);
    for (const property of ["muted", "solo"]) row.querySelector(`[data-property="${property}"]`).setAttribute("aria-pressed", String(track[property]));
    const volume = row.querySelector("input");
    if (document.activeElement !== volume) volume.value = track.volume;
    row.classList.toggle("inaudible", !track.audible);
  }
  const style = status.styles.find(item => item.id === status.style);
  $("#style-source-attribution").textContent = style?.provenance ?? "";
  $("#style-source-patterns").textContent = Object.entries(controls.source_patterns).map(([section, patterns]) => `${section.replaceAll("_", " ")}: ${patterns.length} source chord pattern${patterns.length === 1 ? "" : "s"}`).join(" · ");
}
for (const kind of ["intro", "ending"]) $(`#style-${kind}-choice`).addEventListener("change", event => arrangerCommand(`${kind}_select`, Number(event.target.value)));
$("#style-mix-reset").addEventListener("click", () => arrangerCommand("mix_reset"));
