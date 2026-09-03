# Development with Pipenv

Pipenv is the supported dependency-management workflow. `Pipfile` declares
direct runtime/development dependencies and `Pipfile.lock` pins the complete
resolved environment for reproducible installation. `pyproject.toml` remains
the package/build metadata and defines the `ostinato` console command.

## First setup

Install Python 3.12 and Pipenv using your normal OS or user-level package
management. From the repository root:

```bash
export PIPENV_VENV_IN_PROJECT=1
pipenv sync --dev
pipenv run ostinato --help
pipenv run scripts/run-checks.sh
```

`PIPENV_VENV_IN_PROJECT=1` keeps the environment in the ignored `.venv/`
directory. It is optional; without it, Pipenv stores the environment in its
normal per-user location.

If `.venv` already exists but was not created by Pipenv, it can still be used
when its Python version is correct. For a clean recreation, remove that local
environment yourself and run `pipenv sync --dev` again; never commit `.venv`.

## Everyday commands

```bash
pipenv run ostinato doctor
pipenv run ostinato keyboard
pipenv run pytest
pipenv run ruff check .
pipenv run ruff format --check .
pipenv run mypy src tests
```

`pipenv shell` is available if an activated shell is preferred, but `pipenv
run` makes the selected environment explicit and works well in scripts and
CI.

## Changing dependencies

Add a runtime dependency:

```bash
pipenv install package-name
```

Add a development-only dependency:

```bash
pipenv install --dev package-name
```

After reviewing the resulting `Pipfile` and `Pipfile.lock`, run all checks. To
install exactly what is locked without updating versions, use `pipenv sync
--dev`. Use `pipenv verify` to confirm that the lock matches the declaration.

System packages such as FluidSynth and ALSA utilities remain outside Pipenv.
Review `scripts/bootstrap-ubuntu.sh`; it prints suggested Ubuntu commands but
does not execute them.

## Local KORG style research

KORG style packages, exported MIDI, and converted files are user-supplied local
assets and are ignored by Git. The tracked workflow is documented in
[`assets/styles/korg/README.md`](../assets/styles/korg/README.md).

```bash
pipenv run python scripts/download_korg_styles.py
pipenv run python scripts/extract_korg_styles.py
pipenv run python scripts/inspect_korg_styles.py
pipenv run python scripts/import_korg_style.py assets/styles/korg/midi/example.mid
pipenv run python scripts/import_korg_style.py \
  assets/styles/korg/midi/example \
  --name "Example Style" \
  --source-file "USER01.STY#1"
pipenv run python scripts/render_imported_style.py \
  assets/styles/korg/midi/example \
  --name "Example Style" \
  --soundfont /exact/path/to/configured.sf2 \
  --output assets/styles/korg/converted/example/variation-1-cv1.wav
```

The first command lists approved official catalog pages; it does not scrape or
download mutable URLs. The extractor rejects archive traversal and preserves
existing files unless `--force` is explicit. The binary inspector records
structural clues without treating `.STY` as MIDI. The importer accepts either
a marker-based SMF or a directory of per-Chord-Variation format-0 SMFs using
KORG's documented Pa80 filenames and style channels. It reports that neither
path authenticates origin from bytes alone and does not claim native `.STY`
decoding. For the validated legacy `KORF` directory variants observed in
official KORG packages, the inspector can list bank display names in the same
physical order used by KORG's converter. This catalog probe is not a
musical-data decoder.

The offline renderer preserves source pitch and uses an explicitly supplied
General MIDI SoundFont as a listening approximation. It does not infer KORG
patches, source chords, or proprietary note-transposition rules. Imported JSON,
exported MIDI, and rendered WAV files remain ignored local derivatives.

At runtime, `OSTINATO_KORG_STYLE_DIRECTORY` identifies the read-only directory
of converted `*/style.json` documents. Compose maps the local `converted/`
directory there without copying it into the image. The live arranger exposes
Variation 1 CV1, Intro 1 CV1, Fill 1/2 CV1, and Ending 1 CV1, using the explicit
Ostinato chord policy recorded in
[`w39-korg-live-library.md`](evidence/w39-korg-live-library.md). Drum and
percussion pitches are never transposed; melodic programs are General MIDI
approximations rather than original KORG patches.

Imported documents may declare a stable `library_group`. The arranger API
exposes that group and the browser first selects a group, then filters the style
selector to that group. Run `scripts/audit_korg_styles.py --fail-on-duplicates`
to reject exact duplicates across the five live CV1 sections.
