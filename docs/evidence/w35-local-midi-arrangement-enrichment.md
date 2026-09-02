# W35 — local MIDI arrangement enrichment

Status: corpus-analysis, complete software, and deployed-software gates
complete; performer listening gate pending.

## Scope

Analyze the user-provided `~/projects/Mid` library without modifying or
redistributing it, identify aggregate accompaniment practices, and enrich the
four-bar built-in arrangements. Full method, statistics, limitations, and
musical findings are in `docs/midi-library-analysis.md`.

## Implemented behavior

- Every built-in comping part now changes between two-note shells, close
  voicings, open voicings, and style-appropriate dominant color.
- Explicit main-section melodic answers are monophonic chord-tone phrases,
  leaving room for the live accordion lead.
- Country, Reggae, Samba, Cha-Cha, and Blues now have materially different
  bass, chord, and drum/percussion grids across their four measures.
- The timeline consumes the same enriched groove objects, so the live and
  designer visualizations reflect the added events without a separate display
  approximation.

## Focused automated evidence

- `62 passed` across procedural, sampled, and SFZ renderer tests.
- New tests require at least three distinct accompaniment bars in each formerly
  repetitive style, chord-safe 2/3/4-note voicing variety, monophonic normal
  answer attacks, and different sampled comp voice counts across a phrase.
- Complete local suite: `175 passed`; Ruff formatting/lint, strict mypy,
  browser tests, `git diff --check`, and Compose configuration validation passed.

## Evidence boundary and human gate

- Local corpus inspection and aggregate statistics: **observed by software**.
- Source licensing/ownership: **unknown**; no MIDI data or passages are bundled.
- Physical FR-4X and speaker route: **untested**.
- Musical richness, balance, and playability: **pending** performer listening.

## Deployed-software evidence

- The final image rebuilt, the service was recreated, Compose reached
  `healthy`, and `/api/health` returned `{"status":"ok"}`.
- Real sfizz four-bar renders inside the deployed container were non-silent and
  had zero clipped samples for Classic Tango, Classic Waltz, Swing Foxtrot,
  Country Two-Step, Reggae One Drop, Brazilian Samba, New Orleans Cha-Cha, and
  Blues Shuffle. Peaks ranged from `-7.18` to `-1.77 dBFS`.
- The deployed Samba timeline reports four bars with 26 bass and 22 comp events,
  confirming the enriched groove reached the shared visualization API.
- Final arranger state: `running=false`, `section=stopped`, style
  `modern_tango`, synthesis engine `sfizz · open sampled genre ensemble`, and no
  arranger error.
