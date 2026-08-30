"""Validated, atomic persistence for user-designed accompaniment styles."""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from ostinato.computer_audio import DEMO_STYLES
from ostinato.keyboard_input import MAX_TEMPO_BPM, MIN_TEMPO_BPM

CUSTOM_STYLE_SCHEMA_VERSION = 2
CUSTOM_STYLE_ID = re.compile(r"^custom-[a-f0-9]{12}$")
LAYER_NAMES = ("bass", "comp", "fill", "backing")


@dataclass(frozen=True, slots=True)
class InstrumentDefinition:
    """One curated General MIDI instrument exposed by the designer."""

    id: str
    name: str
    category: str
    program: int | None
    note_offset: int = 0
    gate_scale: float = 1.0


INSTRUMENTS: dict[str, InstrumentDefinition] = {
    instrument.id: instrument
    for instrument in (
        InstrumentDefinition("none", "Off", "Control", None),
        InstrumentDefinition("piano", "Acoustic grand piano", "Keys", 0),
        InstrumentDefinition("bright_piano", "Bright acoustic piano", "Keys", 1),
        InstrumentDefinition("electric_piano", "Electric piano", "Keys", 4),
        InstrumentDefinition("harpsichord", "Harpsichord", "Keys", 6),
        InstrumentDefinition("vibraphone", "Vibraphone", "Keys", 11),
        InstrumentDefinition("nylon_guitar", "Nylon acoustic guitar", "Guitars", 24),
        InstrumentDefinition("acoustic_guitar", "Steel acoustic guitar", "Guitars", 25),
        InstrumentDefinition("jazz_guitar", "Jazz electric guitar", "Guitars", 26),
        InstrumentDefinition("clean_guitar", "Clean electric guitar", "Guitars", 27),
        InstrumentDefinition("muted_guitar", "Muted electric guitar", "Guitars", 28),
        InstrumentDefinition(
            "mandolin",
            "Mandolin-style pluck",
            "Guitars",
            25,
            note_offset=12,
            gate_scale=0.55,
        ),
        InstrumentDefinition("double_bass", "Double bass", "Bass", 32),
        InstrumentDefinition("fingered_bass", "Bass guitar · fingered", "Bass", 33),
        InstrumentDefinition("picked_bass", "Bass guitar · picked", "Bass", 34),
        InstrumentDefinition("fretless_bass", "Fretless bass guitar", "Bass", 35),
        InstrumentDefinition("violin", "Violin", "Strings", 40),
        InstrumentDefinition("viola", "Viola", "Strings", 41),
        InstrumentDefinition("cello", "Cello", "Strings", 42),
        InstrumentDefinition("contrabass", "Orchestral contrabass", "Strings", 43),
        InstrumentDefinition("tremolo_strings", "Tremolo strings", "Strings", 44),
        InstrumentDefinition("pizzicato_strings", "Pizzicato strings", "Strings", 45),
        InstrumentDefinition("orchestral_harp", "Orchestral harp", "Strings", 46),
        InstrumentDefinition("string_ensemble", "String ensemble", "Strings", 48),
        InstrumentDefinition("slow_strings", "Slow string ensemble", "Strings", 49),
        InstrumentDefinition("oboe", "Oboe", "Winds", 68),
        InstrumentDefinition("english_horn", "English horn", "Winds", 69),
        InstrumentDefinition("clarinet", "Clarinet", "Winds", 71),
        InstrumentDefinition("piccolo", "Piccolo", "Winds", 72),
        InstrumentDefinition("flute", "Flute", "Winds", 73),
        InstrumentDefinition("recorder", "Recorder", "Winds", 74),
    )
}


class CustomStyleError(RuntimeError):
    """A custom style was invalid or could not be persisted safely."""


@dataclass(frozen=True, slots=True)
class LayerSettings:
    """Instrument and level for one arranger role."""

    instrument: str
    volume: int
    octave: int = 0
    gate_percent: int = 100

    @classmethod
    def from_mapping(cls, value: object, label: str) -> LayerSettings:
        if not isinstance(value, Mapping):
            raise CustomStyleError(f"{label} layer must be an object")
        instrument = value.get("instrument")
        volume = value.get("volume")
        octave = value.get("octave", 0)
        gate_percent = value.get("gate_percent", 100)
        if not isinstance(instrument, str) or instrument not in INSTRUMENTS:
            raise CustomStyleError(f"{label} uses an unsupported instrument")
        if type(volume) is not int or not 0 <= volume <= 100:
            raise CustomStyleError(f"{label} volume must be from 0 through 100")
        if type(octave) is not int or not -2 <= octave <= 2:
            raise CustomStyleError(f"{label} octave must be from -2 through 2")
        if type(gate_percent) is not int or not 20 <= gate_percent <= 150:
            raise CustomStyleError(
                f"{label} note length must be from 20 through 150 percent"
            )
        return cls(instrument, volume, octave, gate_percent)


@dataclass(frozen=True, slots=True)
class CustomStyle:
    """One saved palette and mix applied to a built-in rhythmic template."""

    id: str
    name: str
    base_style_id: str
    beats_per_bar: int
    phrase_bars: int
    tempo_bpm: int
    bass: LayerSettings
    comp: LayerSettings
    fill: LayerSettings
    backing: LayerSettings
    drums_enabled: bool
    drums_volume: int
    schema_version: int = CUSTOM_STYLE_SCHEMA_VERSION

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, object],
        *,
        require_id: bool = True,
    ) -> CustomStyle:
        identifier = value.get("id")
        if not require_id and identifier is None:
            identifier = f"custom-{uuid.uuid4().hex[:12]}"
        if not isinstance(identifier, str) or not CUSTOM_STYLE_ID.fullmatch(identifier):
            raise CustomStyleError("custom style id is invalid")
        if value.get("schema_version", CUSTOM_STYLE_SCHEMA_VERSION) not in (1, 2):
            raise CustomStyleError("unsupported custom style schema")
        name = value.get("name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise CustomStyleError("style name must contain 1 through 80 characters")
        base_style_id = value.get("base_style_id")
        if not isinstance(base_style_id, str) or base_style_id not in DEMO_STYLES:
            raise CustomStyleError("style must use a known rhythmic template")
        template = DEMO_STYLES[base_style_id]
        beats_per_bar = value.get("beats_per_bar", template.beats_per_bar)
        if beats_per_bar is None:
            beats_per_bar = template.beats_per_bar
        if type(beats_per_bar) is not int or beats_per_bar != template.beats_per_bar:
            raise CustomStyleError(
                f"{template.name} requires a {template.beats_per_bar}/4 measure"
            )
        phrase_bars = value.get("phrase_bars", 4)
        if type(phrase_bars) is not int or not 1 <= phrase_bars <= 4:
            raise CustomStyleError("phrase must contain 1 through 4 measures")
        tempo_bpm = value.get("tempo_bpm")
        if (
            type(tempo_bpm) is not int
            or not MIN_TEMPO_BPM <= tempo_bpm <= MAX_TEMPO_BPM
        ):
            raise CustomStyleError(
                f"style tempo must be from {MIN_TEMPO_BPM} through {MAX_TEMPO_BPM}"
            )
        drums_enabled = value.get("drums_enabled")
        drums_volume = value.get("drums_volume")
        if not isinstance(drums_enabled, bool):
            raise CustomStyleError("drums_enabled must be true or false")
        if type(drums_volume) is not int or not 0 <= drums_volume <= 100:
            raise CustomStyleError("drums volume must be from 0 through 100")
        return cls(
            id=identifier,
            name=name.strip(),
            base_style_id=base_style_id,
            beats_per_bar=beats_per_bar,
            phrase_bars=phrase_bars,
            tempo_bpm=tempo_bpm,
            bass=LayerSettings.from_mapping(value.get("bass"), "bass"),
            comp=LayerSettings.from_mapping(value.get("comp"), "comp"),
            fill=LayerSettings.from_mapping(value.get("fill"), "fill"),
            backing=LayerSettings.from_mapping(value.get("backing"), "backing"),
            drums_enabled=drums_enabled,
            drums_volume=drums_volume,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def layer(self, name: str) -> LayerSettings:
        if name not in LAYER_NAMES:
            raise CustomStyleError(f"unknown style layer: {name}")
        return getattr(self, name)  # type: ignore[no-any-return]


def default_custom_style_payload(
    base_style_id: str = "modern_tango",
) -> dict[str, object]:
    """Return the user-requested piano, guitar, drum, and flute ensemble."""

    definition = DEMO_STYLES[base_style_id]
    return {
        "schema_version": CUSTOM_STYLE_SCHEMA_VERSION,
        "name": f"My {definition.name}",
        "base_style_id": base_style_id,
        "beats_per_bar": definition.beats_per_bar,
        "phrase_bars": 4,
        "tempo_bpm": definition.default_tempo_bpm,
        "bass": {
            "instrument": "acoustic_guitar",
            "volume": 82,
            "octave": 0,
            "gate_percent": 85,
        },
        "comp": {
            "instrument": "piano",
            "volume": 88,
            "octave": 0,
            "gate_percent": 90,
        },
        "fill": {
            "instrument": "flute",
            "volume": 58,
            "octave": 0,
            "gate_percent": 100,
        },
        "backing": {
            "instrument": "acoustic_guitar",
            "volume": 48,
            "octave": 0,
            "gate_percent": 75,
        },
        "drums_enabled": True,
        "drums_volume": 76,
    }


def default_custom_styles_path() -> Path:
    configured = os.environ.get("OSTINATO_STATE_DIRECTORY")
    directory = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".local" / "state" / "ostinato"
    )
    return directory / "custom-styles.json"


class CustomStyleStore:
    """Atomically persist the complete collection of user-designed styles."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_custom_styles_path()

    def load(self) -> tuple[CustomStyle, ...]:
        if not self.path.exists():
            return ()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise CustomStyleError(f"could not read custom styles: {error}") from error
        if not isinstance(value, dict) or value.get("schema_version") not in (1, 2):
            raise CustomStyleError("unsupported custom styles document")
        styles = value.get("styles")
        if not isinstance(styles, list):
            raise CustomStyleError("custom styles must be a list")
        loaded = tuple(
            CustomStyle.from_mapping(item)
            for item in styles
            if isinstance(item, Mapping)
        )
        if len(loaded) != len(styles):
            raise CustomStyleError("every saved custom style must be an object")
        if len({style.id for style in loaded}) != len(loaded):
            raise CustomStyleError("custom style ids must be unique")
        return loaded

    def create(self, value: Mapping[str, object]) -> CustomStyle:
        styles = list(self.load())
        style = CustomStyle.from_mapping(value, require_id=False)
        styles.append(style)
        self._save(styles)
        return style

    def update(self, identifier: str, value: Mapping[str, object]) -> CustomStyle:
        styles = list(self.load())
        replacement_value = dict(value)
        replacement_value["id"] = identifier
        replacement = CustomStyle.from_mapping(replacement_value)
        for index, style in enumerate(styles):
            if style.id == identifier:
                styles[index] = replacement
                self._save(styles)
                return replacement
        raise CustomStyleError(f"custom style does not exist: {identifier}")

    def delete(self, identifier: str) -> None:
        styles = list(self.load())
        retained = [style for style in styles if style.id != identifier]
        if len(retained) == len(styles):
            raise CustomStyleError(f"custom style does not exist: {identifier}")
        self._save(retained)

    def _save(self, styles: Sequence[CustomStyle]) -> None:
        value = {
            "schema_version": CUSTOM_STYLE_SCHEMA_VERSION,
            "styles": [style.to_dict() for style in styles],
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                text=True,
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump(value, stream, indent=2, sort_keys=True)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)
        except OSError as error:
            raise CustomStyleError(f"could not save custom styles: {error}") from error
