"""Versioned, atomic persistence for one guided MIDI calibration profile."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

JsonObject = dict[str, object]
PROFILE_SCHEMA_VERSION = 1


class MidiProfileStoreError(RuntimeError):
    """A saved profile could not be read or written safely."""


def default_profile_path() -> Path:
    """Return the configured state path without creating it."""

    configured = os.environ.get("OSTINATO_STATE_DIRECTORY")
    directory = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".local" / "state" / "ostinato"
    )
    return directory / "midi-profile.json"


class MidiProfileStore:
    """Persist a single profile with same-directory atomic replacement."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_profile_path()

    def load(self) -> JsonObject | None:
        """Load the profile, returning ``None`` when none has been saved."""

        if not self.path.exists():
            return None
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise MidiProfileStoreError(
                f"could not read MIDI profile: {error}"
            ) from error
        if not isinstance(value, dict):
            raise MidiProfileStoreError("saved MIDI profile must be a JSON object")
        if value.get("schema_version") != PROFILE_SCHEMA_VERSION:
            raise MidiProfileStoreError(
                "saved MIDI profile has an unsupported schema version"
            )
        return {str(key): item for key, item in value.items()}

    def save(self, profile: Mapping[str, object]) -> JsonObject:
        """Atomically replace the saved profile and return its JSON value."""

        value = dict(profile)
        if value.get("schema_version") != PROFILE_SCHEMA_VERSION:
            raise MidiProfileStoreError(
                "refusing to save an unsupported profile schema"
            )
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
            raise MidiProfileStoreError(
                f"could not save MIDI profile: {error}"
            ) from error
        return value

    def clear(self) -> None:
        """Remove the saved profile when it exists."""

        try:
            self.path.unlink(missing_ok=True)
        except OSError as error:
            raise MidiProfileStoreError(
                f"could not clear MIDI profile: {error}"
            ) from error
