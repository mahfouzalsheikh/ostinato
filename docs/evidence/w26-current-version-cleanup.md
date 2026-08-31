# W26 — Current-version cleanup and documentation

Status: software gate complete; documentation review pending.

## Scope

Remove abandoned implementation paths and historical milestone clutter while
preserving the current Dockerized web arranger. Replace the project overview
with current operating documentation and sanitized product screenshots.

## Cleanup

- Removed the superseded MIDI-arranger output/probing branch and its tests. The
  maintained arranger produces accompaniment through the selected host audio
  sink; optional MIDI output remains limited to browser-surface notes.
- Removed unused YAML configuration examples, recording scaffolding, the
  obsolete style-format stub, and evidence reports W1–W24.
- Removed direct PyYAML and typing-stub dependencies after confirming that no
  maintained module imports them. A transitive PyYAML package may still appear
  in the resolved lock file through another dependency.
- Replaced the historical execution sequence with the current maintenance plan.
- Kept W25 as the style-library provenance and licensing record.

## Documentation

- Rewrote `README.md` around the maintained product: capabilities, signal flow,
  style catalog, designer, Docker setup, first-run workflow, controls,
  architecture, persistence, safety boundaries, and current limitations.
- Added three sanitized screenshots under `docs/screenshots/` for the arranger,
  complete accordion surface, and style designer. They contain no saved MIDI
  port or host-device names.
- Prepared a long-form article and a short share post as private local drafts.
  Both are ignored by Git and Docker and are not tracked project content.

## Verification

- **automated:** `pipenv run scripts/run-checks.sh` passed with 136 tests,
  browser JavaScript checks, Ruff formatting/linting, and strict mypy.
- **automated:** `git diff --check` passed and every local documentation link
  referenced by the README and article drafts resolved to an existing file.
- **deployed software:** `docker compose up -d --build` completed from the
  cleaned tree. The recreated service became healthy; `/api/health` returned
  `{"status":"ok"}` and the live arranger API reported fourteen styles,
  stopped transport, no active preview, and no backend error.
- **observed:** the three screenshots were captured from the live application
  and visually inspected for layout and accidental machine-specific details.
- **pending:** owner review of the README wording, screenshots, and private
  LinkedIn drafts.
- **untested:** no claim is made here about physical FR-4X MIDI, Bluetooth/ALSA
  audio, acoustic latency, or performer listening quality.

## Recovery and release boundary

The removed tracked files remain recoverable from Git history. No commit or push
is part of this milestone until the documentation review gate is accepted; the
two LinkedIn drafts must remain outside any future commit.
