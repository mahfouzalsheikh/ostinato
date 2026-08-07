#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
Project Ostinato Ubuntu preparation (dry run)

Review and run these commands yourself if the listed packages are missing:

  sudo apt update
  sudo apt install fluidsynth fluid-soundfont-gm alsa-utils pipewire-audio \
    python3-venv python3-dev build-essential libasound2-dev

Then create the project environment without sudo:

  export PIPENV_VENV_IN_PROJECT=1
  pipenv sync --dev
  pipenv run scripts/run-checks.sh
  pipenv run ostinato doctor

This script is intentionally non-mutating and did not install anything.
EOF
