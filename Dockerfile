# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIPENV_VENV_IN_PROJECT=1

WORKDIR /app

# Keep compilers and headers out of the runtime image while still allowing
# python-rtmidi to build on architectures without a compatible wheel.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        libasound2-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir pipenv==2026.0.3

COPY Pipfile Pipfile.lock pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pipenv verify \
    && pipenv sync


FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ALSA tools drive/probe host sound devices, FluidSynth is the planned synth,
# and usbutils makes the explicitly passed-through USB bus inspectable.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        alsa-utils \
        fluidsynth \
        usbutils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
COPY . .

ENTRYPOINT ["ostinato"]
CMD ["--help"]
