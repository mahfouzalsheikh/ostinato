# Verified legacy style exports

This optional, disposable container drives KORG's official Pa80 Style to MIDI
1.06 application. It contains no KORG executable or style material. Obtain the
utility separately from the official source and verify its checksum before use.
The W38/W45 evidence records the version and checksum actually exercised.

The Win32 helper reads the application's actual style and section tree. The
Python driver verifies the bank slot name, loaded style name, and proposed MIDI
filename before saving every displayed Chord Variation. It does not decode
proprietary musical data. The toolbar coordinates belong to this particular
utility and virtual display; unexpected dialogs fail the run.

Build with `docker build -t ostinato-style-converter scripts/korg_converter`.
Create a disposable workspace containing `tool/PaStyleToMidi.exe` and
`jobs.json`. Each job has `id` (a safe directory slug), `bank` (a relative path
beneath the KORG asset workspace), `slot` (one-based converter slot), `name`
(the catalog name), and `package` (provenance). Generate the job list from
`probe_korf_bank_catalog`; review the compatibility boundary before running it.

Mount that workspace at `/work` and the local KORG workspace read-only at
`/assets`. Start the image without MIDI/audio devices, then run:

```bash
CONVERTER_WORKSPACE=/exact/path/to/workspace \
CONVERTER_CONTAINER=actual-container-name \
python scripts/korg_converter/export.py
```

Exports and per-style completion manifests are written beneath `verified/`.
The manifests record all converter-visible patterns and invalid MIDI headers.
Use `WORKER_ID` (zero-based) and `WORKER_COUNT` with separate containers to
partition one job list. Each partition must have exclusive ownership of its
output styles. Completed styles can be resumed. Interrupted partial exports
must pass the strict importer before promotion.

Run `scripts/import_korg_style.py` on each completed export directory. Preserve
existing source IDs and archive the previous library before replacing local
JSON. Re-run `scripts/audit_korg_styles.py --fail-on-duplicates`: its fingerprint
now covers every exported section and Chord Variation. Stop and remove only the
disposable containers and image created for this operation when finished.
