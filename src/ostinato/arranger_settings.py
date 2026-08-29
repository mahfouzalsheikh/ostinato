"""Atomic persistence for explicitly confirmed arranger MIDI routing."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

SETTINGS_SCHEMA_VERSION = 1


class ArrangerSettingsStoreError(RuntimeError):
    """Saved arranger routing could not be read or written safely."""


def default_settings_path() -> Path:
    configured = os.environ.get("OSTINATO_STATE_DIRECTORY")
    directory = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".local" / "state" / "ostinato"
    )
    return directory / "arranger-routing.json"


class ArrangerSettingsStore:
    """Persist one confirmed FR-4X sound-module routing."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_settings_path()

    def load(self) -> dict[str, object] | None:
        if not self.path.exists():
            return None
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ArrangerSettingsStoreError(
                f"could not read arranger routing: {error}"
            ) from error
        if not isinstance(value, dict):
            raise ArrangerSettingsStoreError("arranger routing must be a JSON object")
        if value.get("schema_version") != SETTINGS_SCHEMA_VERSION:
            raise ArrangerSettingsStoreError("unsupported arranger routing schema")
        return {str(key): item for key, item in value.items()}

    def save(self, settings: Mapping[str, object]) -> dict[str, object]:
        value = dict(settings)
        if value.get("schema_version") != SETTINGS_SCHEMA_VERSION:
            raise ArrangerSettingsStoreError("unsupported arranger routing schema")
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
            raise ArrangerSettingsStoreError(
                f"could not save arranger routing: {error}"
            ) from error
        return value
