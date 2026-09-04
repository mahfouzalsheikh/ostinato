FROM debian:bookworm-slim
RUN dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get install --yes --no-install-recommends \
       wine wine32:i386 xvfb xdotool imagemagick gcc-mingw-w64-i686 \
    && rm -rf /var/lib/apt/lists/*
COPY ui.c /opt/converter-ui.c
RUN i686-w64-mingw32-gcc /opt/converter-ui.c -o /opt/converter-ui.exe -lcomctl32
ENV WINEARCH=win32 WINEPREFIX=/wine DISPLAY=:99 WINEDEBUG=-all
CMD ["sh", "-c", "Xvfb :99 -screen 0 1280x900x24 & sleep 1; wine /work/tool/PaStyleToMidi.exe"]
