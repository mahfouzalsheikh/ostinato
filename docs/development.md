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

