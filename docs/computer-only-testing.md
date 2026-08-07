# Computer-only testing

The computer-keyboard input source allows development without an accordion,
MIDI interface, audio interface, or FluidSynth. It bypasses FR-4X MIDI mapping
and creates normalized chord states directly.

```text
computer keyboard -----> normalized ChordState -----> future arranger engine

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
Command:  Space=clear    p=panic    ?=help    q=quit
```

Select a quality and then a root. Selecting another quality while a root is
active emits the updated chord immediately. Each change prints the normalized
chord that a future planner will receive.

Panic is currently a diagnostic event because no MIDI output sink exists yet.
Likewise, this command does not produce accompaniment audio in the current P0
slice. It tests input behavior and the shared chord-state contract.

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
changes, and future arranger logic without hardware. It cannot validate FR-4X
channels/messages, USB latency, audio latency, scheduler timing on stage
hardware, SoundFont behavior, or musical feel.

