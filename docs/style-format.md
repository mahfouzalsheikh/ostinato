# Style format v1 (design contract)

Implementation starts in OST-011. This document records the schema boundary so
later scheduling and harmonization do not acquire implicit semantics.

A manifest must declare:

- schema version, style name, default tempo, time signature, and MIDI ticks per
  quarter;
- each section's MIDI file, bar length, loop behavior, and legal successors;
- each track's role, source/output channel, bank/program, level, pan, and mute;
- reference root and quality for pitched material;
- one transform policy per track: `fixed`, `drums`, `root_transpose`, or
  `chord_tone_map`;
- note range and octave-wrap policy; and
- transition quantization and fill destination.

Version 1 excludes tempo maps, guitar modes, chord-scale rules, proprietary
imports, and undocumented transformations.

