import {
  PIANO_FIRST_PITCH_CLASS,
  PIANO_KEY_COUNT,
  inferPianoBase,
} from "./midi-surface.js";
import {
  STRADELLA_COLUMN_COUNT,
  STRADELLA_ROW_COUNT,
  centralStradellaColumn,
  classifyChordNotes,
  stradellaBassButtonsForPitch,
  stradellaCell,
} from "./stradella.js";

const BASS_ROW_COUNT = STRADELLA_ROW_COUNT;
const BASS_COLUMN_COUNT = STRADELLA_COLUMN_COUNT;
const BLACK_PITCH_CLASSES = new Set([1, 3, 6, 8, 10]);

const template = document.createElement("template");
template.innerHTML = `
  <style>
    :host {
      display: block;
      min-width: 860px;
      user-select: none;
      -webkit-user-select: none;
      --active-in: #65f6d1;
      --active-out: #ffb758;
    }

    * { box-sizing: border-box; }

    .instrument {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      border: 1px solid #3a4142;
      border-radius: 34px;
      overflow: hidden;
      background: #030405;
      box-shadow: 0 30px 70px rgba(0, 0, 0, .55), inset 0 2px rgba(255, 255, 255, .12);
    }

    .end {
      position: relative;
      overflow: hidden;
      background:
        linear-gradient(100deg, transparent, rgba(255,255,255,.08) 48%, transparent 51%),
        linear-gradient(145deg, #171b1c, #020303 56%, #111516);
    }

    .end::after {
      position: absolute;
      inset: 12px;
      border: 1px solid rgba(255,255,255,.07);
      border-radius: 20px;
      content: "";
      pointer-events: none;
    }

    .left-end {
      display: flex;
      flex-direction: column;
      min-height: 390px;
      padding: 30px 38px 38px;
      border-top: 5px ridge #65706e;
    }

    .right-end {
      display: grid;
      grid-template-rows: 142px 330px;
      padding: 22px 28px 30px;
      border-bottom: 5px ridge #65706e;
    }

    .hand-label {
      position: relative;
      z-index: 1;
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 18px;
      color: #aab3b1;
      font: 700 9px/1 system-ui, sans-serif;
      letter-spacing: .18em;
      text-transform: uppercase;
    }

    .hand-label span:last-child { color: #596361; }

    .registers {
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 10px;
      width: min(100%, 920px);
      margin: 0 auto 24px;
    }

    .register {
      height: 42px;
      border: 1px solid #3c4443;
      border-radius: 4px;
      background: linear-gradient(#252b2b, #070909);
      box-shadow: inset 0 1px rgba(255,255,255,.1);
    }

    .register:nth-child(4) { background: linear-gradient(#f7f4e8, #b5b5ae); }

    .bass-grid {
      position: relative;
      z-index: 2;
      display: grid;
      flex: 1;
      grid-template-columns: repeat(20, 24px);
      grid-template-rows: repeat(6, 24px);
      align-content: space-between;
      justify-content: space-between;
      width: min(100%, 1180px);
      min-height: 250px;
      padding: 30px 42px;
      margin: 0 auto;
      border-radius: 90px 18px 90px 18px;
      background:
        repeating-linear-gradient(135deg, rgba(255,255,255,.04) 0 1px, transparent 1px 5px),
        #090c0d;
      transform: skewY(-2deg);
    }

    .bass-button {
      width: 24px;
      height: 24px;
      padding: 0;
      border: 1px solid #bbc0b9;
      border-radius: 50%;
      cursor: pointer;
      color: #242827;
      font: 700 6px/1 system-ui, sans-serif;
      letter-spacing: -.03em;
      background: radial-gradient(circle at 32% 28%, #fff, #aaa 55%, #363a39);
      box-shadow: 0 3px 5px #000, inset 0 1px rgba(255,255,255,.65);
      transition: transform 60ms ease, box-shadow 60ms ease, background 60ms ease;
    }

    .bass-button.counterbass,
    .bass-button.bass { border-color: rgba(101, 246, 209, .55); }
    .bass-button.major,
    .bass-button.minor,
    .bass-button.seventh,
    .bass-button.diminished { border-color: rgba(255, 183, 88, .55); }
    .bass-button.active-in {
      background: var(--active-in);
      box-shadow: 0 0 11px var(--active-in);
      transform: scale(.82);
    }
    .bass-button.possible-in {
      border-color: var(--active-in);
      background: radial-gradient(circle at 32% 28%, #eafff9, #79ab9f 58%, #273d38);
      box-shadow: 0 0 0 2px rgba(101, 246, 209, .28), 0 0 12px rgba(101, 246, 209, .55);
      transform: scale(.92);
    }
    .bass-button.active-out {
      background: var(--active-out);
      box-shadow: 0 0 11px var(--active-out);
      transform: scale(.82);
    }

    .control-deck {
      position: relative;
      z-index: 1;
      width: min(100%, 1040px);
      padding: 14px 18px 18px;
      margin: 0 auto;
      border-radius: 20px 20px 8px 8px;
      background:
        repeating-linear-gradient(0deg, transparent 0 8px, rgba(255,255,255,.045) 8px 9px),
        #080b0c;
    }

    .deck-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
      color: #9ba5a3;
      font: 700 8px/1 system-ui, sans-serif;
      letter-spacing: .18em;
      text-transform: uppercase;
    }

    .screen {
      width: 72px;
      height: 28px;
      border: 2px solid #1f2727;
      border-radius: 3px;
      color: #65f6d1;
      font: 700 9px/24px ui-monospace, monospace;
      text-align: center;
      background: #06110f;
      box-shadow: inset 0 0 12px rgba(101,246,209,.14);
    }

    .deck-controls {
      display: grid;
      grid-template-columns: repeat(8, 1fr);
      gap: 7px;
      align-items: end;
    }

    .deck-control {
      height: 48px;
      border: 1px solid #49514f;
      border-radius: 4px 4px 9px 9px;
      background: linear-gradient(#343a39, #090b0c);
      box-shadow: inset 0 1px rgba(255,255,255,.12);
    }

    .deck-control:nth-child(1), .deck-control:nth-child(5), .deck-control:nth-child(8) {
      background: linear-gradient(#f4f2e7, #9c9d98);
    }

    .piano {
      position: relative;
      z-index: 2;
      display: flex;
      width: min(100%, 1320px);
      height: 330px;
      padding: 0 5px 5px;
      margin: 0 auto;
      overflow: hidden;
      border-radius: 0 0 14px 14px;
      background: #050606;
      perspective: 800px;
    }

    .piano-key {
      position: relative;
      padding: 0;
      border: 0;
      cursor: pointer;
      transform-origin: top;
      transition: transform 45ms ease, background 70ms ease, box-shadow 70ms ease;
    }

    .piano-key.white {
      flex: 1 1 0;
      height: 100%;
      border-right: 1px solid #777;
      border-radius: 0 0 5px 5px;
      background: linear-gradient(90deg, #c9cac4, #fff 18%, #f6f5eb 74%, #a7aaa6);
      box-shadow: inset 0 -5px 8px rgba(0,0,0,.18);
    }

    .piano-key.black {
      z-index: 3;
      flex: 0 0 clamp(18px, 2vw, 32px);
      height: 62%;
      margin: 0 clamp(-16px, -1vw, -9px);
      border-right: 2px solid #060707;
      border-bottom: 4px solid #050606;
      border-radius: 0 0 4px 4px;
      background: linear-gradient(90deg, #050606, #262a29 42%, #050606 88%);
      box-shadow: 1px 5px 6px rgba(0,0,0,.75);
    }

    .piano-key.active-in {
      background: linear-gradient(var(--active-in), #2e8470);
      box-shadow: 0 0 18px var(--active-in);
      transform: rotateX(-3deg);
    }
    .piano-key.active-out {
      background: linear-gradient(var(--active-out), #946224);
      box-shadow: 0 0 18px var(--active-out);
      transform: rotateX(-3deg);
    }

    button:focus-visible { outline: 2px solid #65f6d1; outline-offset: 1px; }
  </style>
  <div class="instrument">
    <section class="end right-end" aria-label="37-key right-hand piano keyboard">
      <div class="control-deck" aria-hidden="true">
        <div class="deck-top"><span>Right hand</span><div class="screen">LIVE MIDI</div><span>37 keys</span></div>
        <div class="deck-controls"></div>
      </div>
      <div class="piano"></div>
    </section>
    <section class="end left-end" aria-label="120-button left-hand keyboard">
      <div class="hand-label"><span>Left hand</span><span class="left-mode">Stradella · 2 bass rows</span></div>
      <div class="registers" aria-hidden="true"></div>
      <div class="bass-grid"></div>
    </section>
  </div>
`;

export class Fr4xAccordion extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.append(template.content.cloneNode(true));
    this.pianoBase = null;
    this.trebleChannel = null;
    this.bassChannel = null;
    this.chordChannel = null;
    this.leftByButton = new Map();
    this.activeBassNotes = new Set();
    this.activeBassButtons = new Map();
    this.activeChordNotes = new Set();
    this.activeChordButton = null;
    this.activeChordRoot = null;
    this.chordUpdateTimer = null;
    this.activeInput = new Set();
    this.activeOutput = new Set();
  }

  connectedCallback() {
    this.#buildDecorativeControls();
    this.#buildPiano();
    this.#buildBassButtons();
  }

  #buildDecorativeControls() {
    const registers = this.shadowRoot.querySelector(".registers");
    const deck = this.shadowRoot.querySelector(".deck-controls");
    if (!registers.childElementCount) {
      for (let index = 0; index < 7; index += 1) {
        registers.append(Object.assign(document.createElement("span"), { className: "register" }));
      }
      for (let index = 0; index < 8; index += 1) {
        deck.append(Object.assign(document.createElement("span"), { className: "deck-control" }));
      }
    }
  }

  #buildPiano() {
    const piano = this.shadowRoot.querySelector(".piano");
    if (piano.childElementCount) return;
    // The visual starts on F to reproduce the 22-white/15-black physical
    // pattern visible on the 37-key instrument. It assigns no MIDI note.
    for (let index = 0; index < PIANO_KEY_COUNT; index += 1) {
      const pitchClass = (PIANO_FIRST_PITCH_CLASS + index) % 12;
      const black = BLACK_PITCH_CLASSES.has(pitchClass);
      const key = document.createElement("button");
      key.type = "button";
      key.className = `piano-key ${black ? "black" : "white"}`;
      key.dataset.index = String(index);
      key.setAttribute("aria-label", `Right-hand key ${index + 1}`);
      this.#wireMomentaryControl(key, (active) => {
        this.#setPianoState(index, active, "out");
        this.dispatchEvent(new CustomEvent("surface-note", {
          bubbles: true,
          detail: {
            index,
            active,
            channel: this.trebleChannel,
            note: this.pianoBase == null ? null : this.pianoBase + index,
          },
        }));
      });
      piano.append(key);
    }
  }

  #buildBassButtons() {
    const grid = this.shadowRoot.querySelector(".bass-grid");
    if (grid.childElementCount) return;
    for (let row = 0; row < BASS_ROW_COUNT; row += 1) {
      for (let column = 0; column < BASS_COLUMN_COUNT; column += 1) {
        const id = `r${row + 1}c${column + 1}`;
        const button = document.createElement("button");
        button.type = "button";
        const cell = stradellaCell(row, column);
        button.className = `bass-button ${cell.role}`;
        button.dataset.id = id;
        button.dataset.row = String(row);
        button.dataset.column = String(column);
        button.dataset.rootPitchClass = String(cell.rootPitchClass);
        button.textContent = cell.label;
        button.setAttribute(
          "aria-label",
          `${cell.label}, ${cell.role}, Stradella column ${column + 1}`,
        );
        this.#wireMomentaryControl(button, (active) => this.#handleBassPointer(id, active));
        grid.append(button);
      }
    }
  }

  #wireMomentaryControl(element, callback) {
    element.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      element.setPointerCapture(event.pointerId);
      callback(true);
    });
    const release = (event) => {
      if (element.hasPointerCapture?.(event.pointerId)) {
        element.releasePointerCapture(event.pointerId);
      }
      callback(false);
    };
    element.addEventListener("pointerup", release);
    element.addEventListener("pointercancel", release);
  }

  #handleBassPointer(id, active) {
    const binding = this.leftByButton.get(id);
    if (!binding) {
      if (active) this.dispatchEvent(new CustomEvent("unmapped-button", {
        bubbles: true,
        detail: { id },
      }));
      return;
    }
    this.#setBassState(id, active, "out");
    this.dispatchEvent(new CustomEvent("surface-left", {
      bubbles: true,
      detail: { id, channel: binding.channel, notes: binding.notes, active },
    }));
  }

  configureMidi(profile) {
    this.activeInput.clear();
    this.activeOutput.clear();
    this.shadowRoot.querySelectorAll(".active-in, .possible-in, .active-out").forEach((control) => {
      control.classList.remove("active-in", "possible-in", "active-out");
    });
    this.trebleChannel = profile?.roles?.treble?.primary_channel ?? null;
    this.bassChannel = profile?.roles?.bass?.primary_channel ?? null;
    this.chordChannel = profile?.roles?.chord?.primary_channel ?? null;
    const treble = profile?.roles?.treble;
    const trebleCandidate = treble?.candidates?.find(
      (candidate) => candidate.channel === this.trebleChannel,
    );
    this.pianoBase = inferPianoBase(trebleCandidate?.notes ?? []);
    this.leftByButton.clear();
    this.activeBassNotes.clear();
    this.activeBassButtons.clear();
    this.activeChordNotes.clear();
    this.activeChordButton = null;
    this.activeChordRoot = null;
    clearTimeout(this.chordUpdateTimer);
    this.#updateBassStatus();
  }

  applyMidi(event) {
    if (event.type !== "midi" || event.direction !== "in" || event.note == null) return;
    const active = this.#isNoteOn(event);
    if (this.trebleChannel != null && this.pianoBase != null && event.channel === this.trebleChannel) {
      const index = event.note - this.pianoBase;
      if (index >= 0 && index < PIANO_KEY_COUNT) this.#setPianoState(index, active, "in");
    }
    if (event.channel === this.bassChannel) this.#applyBassEvent(event.note, active);
    if (event.channel === this.chordChannel) this.#applyChordEvent(event.note, active);
  }

  #applyBassEvent(note, active) {
    if (active) {
      this.activeBassNotes.add(note);
    } else {
      this.activeBassNotes.delete(note);
    }
    this.#refreshBassButtons();
  }

  #applyChordEvent(note, active) {
    if (active) this.activeChordNotes.add(note);
    else this.activeChordNotes.delete(note);
    clearTimeout(this.chordUpdateTimer);
    if (!this.activeChordNotes.size) {
      this.#clearActiveChord();
      return;
    }
    if (active) {
      this.chordUpdateTimer = setTimeout(() => this.#updateChordState(), 12);
    }
  }

  #updateChordState() {
    const bassNote = [...this.activeBassNotes].at(-1);
    const chord = classifyChordNotes(
      [...this.activeChordNotes],
      bassNote == null ? null : bassNote % 12,
    );
    if (!chord) return;
    const rowByQuality = { major: 3, minor: 4, seventh: 5, diminished: 6 };
    const column = centralStradellaColumn(chord.rootPitchClass);
    if (column == null) return;
    const id = `r${rowByQuality[chord.quality]}c${column + 1}`;
    if (this.activeChordButton && this.activeChordButton !== id) {
      this.#setBassState(this.activeChordButton, false, "in");
    }
    this.activeChordButton = id;
    this.activeChordRoot = chord.rootPitchClass;
    this.leftByButton.set(id, {
      channel: this.chordChannel,
      notes: [...this.activeChordNotes].sort((left, right) => left - right),
    });
    this.#setBassState(id, true, "in");
    this.#refreshBassButtons();
  }

  #clearActiveChord() {
    if (this.activeChordButton) {
      this.#setBassState(this.activeChordButton, false, "in");
      this.activeChordButton = null;
    }
    this.activeChordRoot = null;
    this.#refreshBassButtons();
  }

  #bassButtonsFor(note) {
    return stradellaBassButtonsForPitch(note % 12, this.activeChordRoot);
  }

  #refreshBassButtons() {
    for (const ids of this.activeBassButtons.values()) {
      for (const id of ids) this.#setBassInputState(id, false, false);
    }
    this.activeBassButtons.clear();
    for (const note of this.activeBassNotes) {
      const ids = this.#bassButtonsFor(note);
      if (!ids.length) continue;
      const ambiguous = ids.length > 1;
      this.activeBassButtons.set(note, ids);
      for (const id of ids) {
        this.leftByButton.set(id, { channel: this.bassChannel, notes: [note] });
        this.#setBassInputState(id, true, ambiguous);
      }
    }
    this.#updateBassStatus();
  }

  #setBassInputState(id, active, possible) {
    const button = this.shadowRoot.querySelector(`.bass-button[data-id="${id}"]`);
    if (!button) return;
    button.classList.remove("active-in", "possible-in");
    if (active) button.classList.add(possible ? "possible-in" : "active-in");
    const signature = `b:${id}`;
    if (active) this.activeInput.add(signature); else this.activeInput.delete(signature);
  }

  #updateBassStatus() {
    const label = this.shadowRoot.querySelector(".left-mode");
    if (!label) return;
    const ambiguous = [...this.activeBassButtons.values()].some((ids) => ids.length > 1);
    if (ambiguous) {
      label.textContent = "Bass row ambiguous · both candidates shown";
    } else if (this.activeBassNotes.size) {
      label.textContent = "Bass row resolved by chord context";
    } else {
      label.textContent = "Stradella · 2 bass rows";
    }
  }

  #isNoteOn(event) {
    return event.message_type === "note_on" && Number(event.velocity) > 0;
  }

  #setPianoState(index, active, direction) {
    const key = this.shadowRoot.querySelector(`.piano-key[data-index="${index}"]`);
    if (!key) return;
    key.classList.toggle(`active-${direction}`, active);
    const signature = `p:${index}`;
    const state = direction === "in" ? this.activeInput : this.activeOutput;
    if (active) state.add(signature); else state.delete(signature);
  }

  #setBassState(id, active, direction) {
    const button = this.shadowRoot.querySelector(`.bass-button[data-id="${id}"]`);
    if (!button) return;
    button.classList.toggle(`active-${direction}`, active);
    const signature = `b:${id}`;
    const state = direction === "in" ? this.activeInput : this.activeOutput;
    if (active) state.add(signature); else state.delete(signature);
  }
}

customElements.define("fr4x-accordion", Fr4xAccordion);

export { BASS_COLUMN_COUNT, BASS_ROW_COUNT, PIANO_KEY_COUNT };
