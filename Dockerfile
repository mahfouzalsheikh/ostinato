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


FROM python:3.12-slim-bookworm AS sfizz-builder

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        git \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --branch 1.2.3 --depth 1 --recurse-submodules --shallow-submodules \
        https://github.com/sfztools/sfizz.git /src/sfizz \
    && test "$(git -C /src/sfizz rev-parse HEAD)" = \
        "4e70dc0bef53b41f2853ed46e26f5911114c92d0" \
    && cmake -S /src/sfizz -B /src/sfizz/build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/sfizz \
        -DSFIZZ_BENCHMARKS=OFF \
        -DSFIZZ_DEMOS=OFF \
        -DSFIZZ_JACK=OFF \
        -DSFIZZ_RENDER=OFF \
        -DSFIZZ_SHARED=ON \
        -DSFIZZ_TESTS=OFF \
    && cmake --build /src/sfizz/build --parallel 2 \
    && cmake --install /src/sfizz/build


FROM python:3.12-slim-bookworm AS sample-assets

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        curl \
        git \
        unzip \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/fetch-open-sfz-assets.sh /usr/local/bin/fetch-open-sfz-assets
RUN bash /usr/local/bin/fetch-open-sfz-assets /opt/ostinato-samples


FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ALSA tools drive/probe direct host devices, PipeWire tools reach desktop and
# Bluetooth sinks through the explicitly mounted user-session socket,
# FluidSynth is the planned synth, and usbutils makes USB inspectable.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        alsa-utils \
        fluidsynth \
        musescore-general-soundfont \
        pipewire-bin \
        timgm6mb-soundfont \
        usbutils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=sfizz-builder /opt/sfizz/ /usr/local/
COPY --from=sample-assets /opt/ostinato-samples/ /opt/ostinato-samples/
# Shinyguitar expects its Aria bank to define $sample_dir. Direct sfizz loading
# bypasses that bank, so resolve the recorded-sample path and provide a second
# preset whose default microphone blend selects the acoustic recordings.
RUN sed --in-place 's|default_path=$sample_dir/|default_path=../Samples/|' \
        '/opt/ostinato-samples/Shinyguitar/Programs/main.sfz' \
    && sed 's/set_cc100=0/set_cc100=127/' \
        '/opt/ostinato-samples/Shinyguitar/Programs/main.sfz' \
        > '/opt/ostinato-samples/Shinyguitar/Programs/acoustic-main.sfz'
RUN ldconfig
# Keep code-dependent environment changes after the large, stable sample layers.
COPY --from=builder /app/.venv /app/.venv
COPY . .

ENTRYPOINT ["ostinato"]
CMD ["--help"]
