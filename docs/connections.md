# Connections and signal flow

## Recommended laptop POC wiring

```text
                         MIDI data only
FR-4X USB COMPUTER  -------------------------->  Linux laptop
                                                      |
                                                      | accompaniment audio
                                                      v
FR-4X analog OUTPUT  --------->  mixer  <------  USB audio interface
                                  |
                                  v
                               PA / headphones
```

The separation is intentional. The performer hears the FR-4X through its
direct analog path even if Ostinato, FluidSynth, the laptop, or the control UI
fails. Ostinato generates accompaniment; it does not process the accordion's
audio.

## FR-4X USB MIDI connection

1. Connect a data-capable cable from the FR-4X **USB COMPUTER** port to the
   laptop. The accordion connector is USB-B. Use USB-B-to-A or USB-B-to-C for
   the laptop as appropriate.
2. Do not use the **USB MEMORY** port; that port is for a flash drive.
3. For Linux, set the FR-4X `USB Drv` setting to `Generic`, then power-cycle the
   instrument so the setting takes effect.
4. Turn on the FR-4X before starting Ostinato or another MIDI application.
5. During diagnosis, use either USB COMPUTER or the five-pin MIDI connection,
   not both to the same computer.
6. Verify enumeration in the normal desktop session:

   ```bash
   lsusb
   aconnect -l
   amidi -l
   pipenv run ostinato doctor
   ```

The USB COMPUTER connection carries MIDI, not FR-4X audio. Roland documents
this behavior in the [FR-4X Reference Manual](https://static.roland.com/assets/media/pdf/FR-4x_reference_e01_W.pdf)
and lists the connector as USB MIDI on the [FR-4X product page](https://www.roland.com/ca/products/fr-4x/).

## FR-4X function switches for arranger control

The recommended no-screen performance path uses the six bass-side function
switches for Intro, Fill In 1, Fill In 2, Ending, Start, and Stop. The FR-4X
Reference Manual documents those assignable functions and notes that function
switch mode repurposes the bass-button column nearest the logo. Configure the
instrument only from its documented settings; Ostinato does not supply guessed
menu values or MIDI encodings.

With the saved accordion input connected, open **Performance controls** in the
Ostinato MIDI setup panel. Learn one assigned switch at a time and save the
result. Ostinato records the exact raw input fingerprint and routes matches in
the backend. Bellows CC11 and musical note, pressure, pitch, timing-clock, and
active-sensing traffic are ineligible. This leaves bellows data available for
future expressive features without making ordinary movement a section trigger.

Before stage use, verify every learned action with accompaniment volume low:
Intro and Start while stopped, both Fill Ins during the main section, Ending
during playback, and Stop. This remains a physical hardware gate; software
tests do not establish what a particular FR-4X configuration transmits.

## Audio connections

- Connect the FR-4X analog output directly to its own mixer input.
- Connect the laptop's selected audio interface output to a different mixer
  input, preferably stereo if the accompaniment style uses stereo positioning.
- Do not depend on the laptop's USB connection for FR-4X audio.
- Start with mixer levels low and establish gain safely before playback.
- Record the exact audio interface, driver, sample rate, buffer size, period
  count, and SoundFont in the milestone evidence.

For latency measurement, capture direct FR-4X analog audio on one recording
channel and synthesized accompaniment on another. Their onset difference is
the measurable end-to-end response; a configured buffer size alone is not a
latency result.

## Raspberry Pi wiring later

The Raspberry Pi replaces the laptop only after the laptop POC passes its
latency, endurance, and rehearsal gates. The same safety boundary remains:
FR-4X analog output goes directly to the mixer, while USB MIDI enters the Pi
and accompaniment audio leaves through the selected Pi audio interface.
