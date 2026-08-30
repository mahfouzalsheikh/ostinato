# Real-time web/MIDI interface

The web interface is a live raw-MIDI monitor and simulator foundation. It uses
native browser Web Components and a FastAPI/WebSocket service; no frontend
build step is required. The local right-hand projection spans the
performer-observed F through upper G (39 key positions), and the left-hand
surface has 120 buttons.

It does **not** contain a default FR-4X MIDI mapping. The instrument supports
multiple bass/chord and free-bass layouts, and the project has not completed
the H1 representative capture gate.

## Run locally

With the locked Pipenv environment installed:

```bash
pipenv run ostinato web
```

Open <http://127.0.0.1:8765>. The host command binds only to loopback unless an
explicit `--host` value is supplied. For the Docker workflow, see
[docker.md](docker.md).

## Connect and detect MIDI

Choose **Set up MIDI** to open the three-step setup wizard:

1. Select an exact ALSA/RtMidi input name and, optionally, an output for the
   browser simulator.
2. Start and stop capture while playing only the requested physical role:
   right-hand treble, left-hand bass buttons, then left-hand chord buttons.
3. Review the ranked observed channels. A channel that appeared in multiple
   phases has lower confidence and remains editable before saving.

The detector does not contain FR-4X channel defaults. The labels come from the
guided performance and the candidates come only from received note-on events.
It detects channel activity and observed note ranges; it does not infer chord
encodings or the physical position of individual left-hand buttons.

Saving writes a versioned profile on the service. On later starts, Ostinato
reconnects only when those exact saved port names are available. A missing port
is reported and never replaced with a different device automatically. The
input can still reconnect when an optional saved output is absent. Run the
wizard again after changing the instrument's MIDI transmission setup.

## Control the live arranger

The arranger panel controls a backend-owned PCM accompaniment process.
Reloading or closing the browser does not stop a running arrangement. The
accordion remains the MIDI input and keeps sending its own analog voice
directly to the mixer. Ostinato synthesizes accompaniment through a separate
computer or USB-interface analog output connected to another mixer input.

Choose **Audio output** before playback:

1. Select one exact host PipeWire sink (including connected Bluetooth audio)
   or a direct `plughw` PCM identifier reported inside the service container.
2. Play the bounded C-major test chord and confirm it reaches the intended
   mixer input.
3. Save the selection. On restart, Ostinato restores it only when the same
   identifier is still present; it never chooses a replacement automatically.

The web arranger does not require FR-4X External Seq. Playback and sends no
arranger MIDI back to the accordion. The optional MIDI output selected in the
MIDI wizard remains only for pressing notes on the browser simulator.

Six original arrangements are available:

- **Modern Tango** — 4/4 at 120 BPM, with a dramatic 3+3+2 foundation,
  changing bass movement, syncopated piano/flute voicings, acoustic guitar, and a
  fourth-bar percussion fill;
- **Classic Tango** — 4/4 at 120 BPM, alternating traditional marcato in four,
  marcato in two, and sincopa gestures across acoustic guitar, piano,
  flute, and short acoustic-guitar attacks without a generic drum kit;
- **Classic Waltz** — 3/4 at 96 BPM, with true bass-on-one and chordal
  oom-pah-pah responses, rising inversions, orchestral dynamics, and a turn
  into the fourth bar;
- **Bossa Nova** — 4/4 at 116 BPM, with steady root/fifth bass on beats one
  and three, independent two-bar syncopated comping, cross-stick accents, and
  a restrained straight-eighth timekeeper;
- **Swing Foxtrot** — 4/4 at 132 BPM, with four-beat walking bass lines,
  offbeat chord stabs, a swung ride-like pulse, and a compact turnaround;
- **Alpine Polka** — 2/4 at 124 BPM, with alternating root/fifth bass,
  offbeat chords, bright flute voicing, and a lively fourth-bar fill.

Choose **Style designer** while playback is stopped to make an editable style.
Select a 2/4, 3/4, or 4/4 measure first; the designer then offers only rhythmic
templates written for that meter instead of squeezing an incompatible pattern
into it. A main phrase can loop its first one through four measures. Intros and
endings retain the template's deliberately arranged four-measure form.

Each of the bass line, chord rhythm, melodic-fill, and backing roles has its own
instrument, level, octave register, and note-length control. The expanded
General MIDI palette includes multiple pianos, acoustic and electric guitars,
fingered/picked/fretless bass guitar, double bass and orchestral contrabass,
solo and ensemble strings, pizzicato/tremolo strings, harp, and woodwinds.
General MIDI has no dedicated mandolin program, so **Mandolin-style pluck** is
explicitly implemented with the steel acoustic-guitar sample, one octave up
and shortened. The six built-in styles remain string-free by default; strings
are now an intentional custom choice.

Saved styles appear in the main selector with a **Custom** label and can be
reopened, updated, or deleted. They are stored atomically in
`custom-styles.json` under `OSTINATO_STATE_DIRECTORY` and require the configured
SoundFont renderer. Schema-v1 custom styles load with neutral register and
note-length defaults and are written as schema v2 on their next save.

The designer's **Preview** strip auditions the complete unsaved form through
the already selected accompaniment audio output. It uses a fixed C-major
harmony so instrument, rhythm, balance, register and articulation comparisons
are repeatable. Preview speed is independent of the saved starting tempo and
can be changed from 40 through 240 BPM; moving it while preview is active
restarts the same form at the new speed. Sound-affecting edits made during
playback automatically restart the audition with a short debounce, so instrument
and range controls can be adjusted without a burst of audio-engine restarts.
Choosing another saved style or a new draft also keeps an active audition going.
**Stop**, closing the modal, saving, deleting, or a normal arranger command
restores the previously selected style, live tempo and harmony. A backend
30-second limit also stops orphaned previews after a browser reload or lost
connection.

The bar-position strip follows the backend audio transport. It renders one
numbered light per quarter-note beat in the selected style (two for 2/4, three
for 3/4, and four for 4/4), highlights beat one in amber, and interpolates
between refreshed integer-tick transport samples so the display does not jump
at the API polling interval.

Each style has a varying four-bar main phrase, its own staged four-bar intro,
and a four-bar ending with a final cadence. Instrument layers have independent
stereo placement and bar-to-bar dynamics. The ending enters at the next bar
and stops after its final bar. Stop playback before changing style. These are
original hard-coded arrangements, not style-v1 files or proprietary imports.
In Docker, their parts are rendered with sampled General MIDI instruments from
the package-provided TimGM6mb SoundFont through native FluidSynth. The older
procedural PCM renderer remains a fallback when no SoundFont is configured.
The genre patterns are original, source-informed arrangements; provenance and
the specific rhythmic principles are recorded in
`docs/evidence/w16-source-informed-styles.md`.

The controls and computer-key equivalents are:

| Control | Key | Behavior |
| --- | --- | --- |
| Intro | `I` | Start the intro, or arm it when left-hand sync is enabled |
| Start | `Enter` | Start the main section from its first bar |
| Stop | `Space` | Stop accompaniment immediately |
| Ending | `E` | Arm the ending for the next bar |
| Left-hand sync | `S` | Toggle automatic start and inactivity stop |

Keyboard shortcuts are ignored while a form control or any setup dialog has
focus.

In **Left-hand auto** mode, the service fuses note-on attacks from both saved
bass and chord channels. A multi-note chord cluster counts as one attack, and
near-simultaneous bass/chord messages are rejected as duplicate timing pulses.
The detector derives possible rhythmic gaps from the selected style's bass and
chord patterns, then requires at least three mutually consistent normalized
intervals. A median/inlier filter rejects isolated timing errors, and later
tempo changes move by at most three BPM per accepted observation rather than
jumping. This lets alternating bass/chord movement, bass-only movement, or
chord-only movement establish tempo without interpreting every MIDI note in a
chord as a separate beat.

Choose **Fixed** to stop left-hand attacks from changing tempo. Drag the rotary
control or focus it and use the arrow keys to choose an exact value from 40 to
240 BPM. Switching back to **Left-hand auto** resets the timing sample while
keeping the current tempo as the interpretation reference.

Chord clusters settle six milliseconds after their first note, and the
backend checks due clusters every five milliseconds. Each new attack is
classified from its own note-on cluster, so lingering note-offs from the prior
chord do not delay or corrupt the next harmony. A new bass note immediately
updates the accompaniment bass voice; when it differs from the chord root the
harmony readout uses slash notation such as `C/G`.

Left-hand sync starts on detected bass or chord activity. It stops after two
complete bars without another left-hand note-on, using the selected style's
meter and current tempo. The grace period prevents ordinary detached bass
playing from stopping accompaniment between strokes.

Chord-channel events are grouped for 12 ms and decoded using normal chord-note
clusters or the documented FR-4X D-Mode ranges. The service uses only the bass
and chord channels reviewed in the saved setup profile. Representative H1
fixtures and physical musical-feel verification remain pending, so this is not
yet production FR-4X recognition evidence.

## Visualize the 39-key piano surface

The saved treble channel and observed note set drive the piano directly; there
is no separate mapping form. The visual keyboard has the locally observed
39-key F-to-G pitch-class shape. Ostinato selects an F-aligned 39-note MIDI window containing
the observed treble notes and centers incomplete samples within that window.
This prevents an arbitrary lowest sampled note from shifting every displayed
pitch. Playing the physical lowest and highest keys during setup removes octave
ambiguity.

Browser piano presses send the corresponding inferred MIDI note on the observed
treble channel through the selected output. A fixed velocity is used for this
provisional simulator.

## Visualize the 120-button Stradella surface

The left surface implements the FR-4X **2 Bass Rows** table: counterbass,
fundamental bass, major, minor, dominant seventh, and diminished rows across 20
circle-of-fifths columns. It is not a free-bass projection. The exact displayed
labels and order follow Roland's reference-manual table.

Incoming notes on the detected bass channel illuminate the central occurrence
of both possible Stradella bass-row buttons. When a recognized chord is active, a
bass note a major third above its root is shown in that chord column's
counterbass row. The FR-4X transmits pitch, not a unique physical button ID, so
a standalone pitch that exists as both a fundamental and counterbass remains
inherently ambiguous; the interface marks both candidates instead of claiming
that one physical switch was observed.

Incoming chord-channel notes are grouped over a short 12 ms window and matched
as major, minor, dominant-seventh, or diminished note sets. The documented
single-note **D-Mode** codes are supported as well. A recognized chord lights
one root/quality button. Browser presses replay only exact bass notes or chord
clusters that have already been observed during the current page session.

This milestone targets the standard two-bass-row Stradella mode. The FR-4X also
offers several three-bass-row Stradella variants; those require an explicit
layout choice before their different row geometry can be displayed safely.

## Real-time and safety boundary

- MIDI callbacks are timestamped with integer monotonic nanoseconds.
- Each browser has a bounded queue; when a slow display fills its queue, the
  oldest display event is discarded rather than blocking MIDI input.
- Browser output accepts only complete, validated MIDI messages.
- Stop, panic, audio-output change, output failure, and shutdown stop or close
  the arranger PCM stream. A browser disconnect also releases MIDI notes that
  its simulator started.
- The WebSocket display is best-effort and is not the accompaniment scheduler.
- No browser timing result is accepted as MIDI/audio latency evidence.
- The web service has no authentication or TLS. Keep the default loopback bind
  unless a separate trusted-network boundary is in place.
- FR-4X analog audio continues directly to the mixer. It never enters this web
  service or the accompaniment container.

## HTTP and WebSocket boundary

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Container/readiness check |
| `GET /api/midi/status` | Available and selected ports |
| `PUT /api/midi/ports` | Select exact input/output names or disconnect |
| `POST /api/midi/send` | Send one validated raw MIDI message |
| `POST /api/midi/detect` | Rank channels from three labeled note captures |
| `GET /api/midi/profile` | Load the saved, versioned detection profile |
| `PUT /api/midi/profile` | Validate and atomically save a reviewed profile |
| `DELETE /api/midi/profile` | Remove the saved profile |
| `GET /api/arranger/status` | Style, tempo, harmony, section, and sync state |
| `POST /api/arranger/command` | Apply one validated local arranger control |
| `GET /api/audio/outputs` | List exact PipeWire/direct-ALSA routes and saved state |
| `PUT /api/audio/output` | Validate and atomically save one exact PCM route |
| `POST /api/audio/test` | Play one bounded test chord through an exact discovered route |
| `WS /ws/midi` | Status, input/output events, and real-time commands |

The API is intentionally local and unauthenticated in this milestone.
