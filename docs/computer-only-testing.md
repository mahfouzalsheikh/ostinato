# Computer-only testing

The computer-keyboard input source allows development without an accordion,
MIDI interface, audio interface, or FluidSynth. It bypasses FR-4X MIDI mapping
and creates normalized chord states directly.

```text
computer keyboard -----> normalized ChordState -----> audible demo arranger
                                                   \-> future style engine

FR-4X USB MIDI --------> capture + verified mapper --^  (later milestone)
```

This separation is important: keyboard mappings are test controls, not assumed
facts about what the FR-4X transmits.

## Interactive use

Run the command in a real terminal:

```bash
pipenv run ostinato keyboard
```

The root keys form a piano-like row:

```text
Root:     a=C  w=C#  s=D  e=Eb  d=E  f=F  t=F#  g=G  y=Ab  h=A  u=Bb  j=B
Quality:  z=major    x=minor    c=dominant-7    v=diminished
Tempo:    -=slower   +=faster   (= also works for unshifted +)
Sections: i=four-bar intro   o=four-bar ending
Command:  Space=clear    p=panic    ?=help    q=quit
```

Select a quality and then a root. Selecting another quality while a root is
active emits the updated chord immediately. Each change prints the normalized
chord that a future planner will receive.

Without `--play`, panic is a diagnostic event and the command tests input
behavior and the shared chord-state contract without opening an audio output.

## Audible computer-only POC

Add `--play` to hear an original modern-tango pattern through the computer's
default ALSA/PipeWire audio route:

```bash
pipenv run ostinato keyboard --play
pipenv run ostinato keyboard --play --tempo 96
```

The command requires `aplay`, which is normally supplied by the host's ALSA
utilities. It deliberately does not select a named device; normal host audio
routing decides where the sound goes. Select a quality and root using the same
keys shown above. The meter is 4/4. Its eight eighth notes are syncopated as
3+3+2, or 1.5+1.5+1 quarter-note beats. Every main-pattern bar carries that
grouping in the bass, piano, kick, percussion accents, and interlocking
reed-like stabs while still resolving at the four-beat bar line.

The procedural ensemble has six separately orchestrated parts: electric-style
bass, percussive piano, a reed/bandoneon-like voice, kick/snare drums,
click/shaker auxiliary percussion, and sustained backing strings. The phrase,
voicings, melody space, and harmony are original; these synthesized timbres are
stand-ins for later SoundFont instruments.

After choosing the starting chord, press `i` to restart with a four-measure
intro. Strings, auxiliary percussion, and a restrained reed voice establish
the opening; piano and bass enter next; drums and the full reed section build
through measures three and four. Press `o` while playing to arm a four-measure
ending. It begins at the next bar, progressively removes drums and percussion,
brings piano, reed, and strings forward, closes on a longer ensemble accent,
and then silences the arranger. Selecting a chord after the ending resumes a
fresh main phrase.

Space silences the arrangement, and `p` silences it and returns the demo
transport to the start. Press `-` to slow down by 5 BPM or `+`/`=` to speed up
by 5 BPM. The live range is 40–240 BPM, and tempo changes preserve the current
musical position.

The demo synthesizes simple waveforms itself, so it does not require
FluidSynth, a SoundFont, MIDI hardware, or an accordion. It is a disposable
audibility harness around the normalized chord boundary—not the production
style engine or final accompaniment sound.

There are no MIDI channels in this procedural demo. In particular, its drums
do not use General MIDI percussion channel 10. The production FluidSynth path
will route drum events by the validated style track configuration; this demo
uses dedicated synthesized ensemble voices instead. The current kick is a
pitched low-frequency transient; the snare and shaker use deterministic shaped
noise rather than pitched General MIDI notes or samples.

The PCM mix applies approximately 8–10 dB of master gain through a soft limiter.
A representative A-minor render measured −2.3 dBFS peak and −16.3 dBFS RMS with
no integer clipping. The host's normal output mixer still controls the final
speaker level.

## Scripted use

`--keys` processes a sequence without taking over the terminal. This is useful
for smoke tests and automated tooling:

```bash
pipenv run ostinato keyboard --keys 'zagxgq'
pipenv run ostinato keyboard --keys 'zagxgq' --json
```

The example selects major, emits C and G, selects minor (emitting G minor),
emits G minor again, and quits. JSON mode writes one object per event and is
suitable for fixtures.

## What this can and cannot prove

It can verify CLI behavior, normalized chord-state handling, rapid scripted
changes, chord-dependent computer audio rendering, and the input boundary
needed by the future arranger without accordion hardware. It cannot validate
FR-4X channels/messages, USB latency, stage audio latency, the future MIDI
scheduler, SoundFont behavior, or musical feel. The audible mode is interactive
only; scripted `--keys` mode remains deterministic and does not start audio.
