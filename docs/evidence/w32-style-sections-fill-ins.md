# W32 — essential instruments, style sections, and Fill Ins

Status: software, native-render, and deployed-software gates complete; owner
listening gate pending.

## Scope

This milestone responds to three performer findings: sampled Tango piano was
masked by its bass, intros and endings reused too much main-loop material, and
the live arranger had no explicit Fill In control.

## Essential-instrument balance

Every non-Waltz sampled profile now declares its essential musical roles. The
Tango profiles explicitly identify piano comping as essential and use a
style-specific rack balance instead of the shared gain values. Country also
records violin as essential; the other rhythm-section genres record the bass,
comping instrument, and percussion roles that anchor their pattern. Classic
Waltz retains the separately accepted six-voice orchestra.

An isolated one-bar render from the final-image candidate measured Modern
Tango piano at `-28.04 dBFS RMS` and bass at `-24.87 dBFS RMS`, versus the W31
four-bar measurements of `-35.02` and `-19.47 dBFS`. Piano therefore moved from
about `15.55 dB` below bass to `3.17 dB` below it. Classic Tango piano measured
`-27.82 dBFS RMS` versus bass at `-25.67 dBFS RMS`. No isolated stem clipped.

These are signal measurements, not proof of perceived balance on the physical
performance system.

## Section arrangement

Intro and ending bars now select different event material from the main loop,
not only different mixer levels. Each style derives those bars from its own
meter and groove vocabulary. Openings progressively introduce rhythm-section
and melodic voices; endings add a lift/turnaround and then reduce to an
unambiguous final cadence.

Tango has an explicit expressive vocabulary: denser piano marcato/sincopa,
violin responses, a staged percussion build, and a lively final launch. Its
ending intensifies across the first three bars before the final bass/chord
cadence. Native renders cover the complete Tango intros, endings, and both Fill
Ins; final clipping results are recorded after the final image build below.

## Fill In behavior

The web surface adds **Fill In 1** (`1`) and **Fill In 2** (`2`). Both are
available only while the main section is playing. The backend queues the chosen
variation at the next measure boundary, reports the queued/current variation in
status, plays exactly one complete bar, and returns to the main phrase.
Variation 1 is a rhythmic lift; variation 2 adds bass and melodic turnaround
movement. An armed ending takes precedence over a Fill In.

## Automated and deployed evidence

- Complete local suite: `162 passed`; Ruff, format, and strict mypy passed.
- Added coverage for section material across all fourteen styles, one-bar
  quantization/clearing in procedural and sampled renderers, service command
  validation, profile intent, Tango piano prominence, and browser controls.
- Native candidate stem audit: both Tango pianos are within `3.2 dB RMS` of
  bass; all ten isolated role renders have zero clipped samples.
- Final image build: passed.
- Final native section audit: Modern Tango intro peak `-1.98 dBFS`, RMS
  `-21.71 dBFS`, clipped samples `0`; Classic Tango intro peak `-4.39 dBFS`,
  RMS `-23.66 dBFS`, clipped samples `0`. Candidate renders of both Tango
  endings and both Fill Ins also had zero clipped samples.
- Recreated service health/API/browser verification: passed. The service is
  healthy at the loopback endpoint, reports the sfizz open-sample genre
  ensemble, serves both Fill In controls, rejects a Fill In while stopped, and
  was left on Modern Tango with stopped transport and no queued fill.
- Physical FR-4X, mixer, amplifier, and speaker behavior: untested.
- Performer realism, balance, section expression, timing, and Fill In
  playability: pending.

## Human gate

The software can establish event timing, role presence, headroom, and deployed
control behavior. The performer must listen to Tango piano in the ensemble,
the style-shaped intros/endings, and both Fill Ins on the actual performance
route before W32 can pass its listening gate.
