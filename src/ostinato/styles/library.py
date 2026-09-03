"""Read-only discovery of host-local imported arranger styles."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ostinato.styles.models import Style, StyleDocumentError, style_from_dict

DEFAULT_IMPORTED_STYLE_DIRECTORY = Path("assets/styles/korg/converted")


class ImportedStyleLibraryError(RuntimeError):
    """A local imported-style library cannot be loaded safely."""


class ImportedStyleLibrary:
    """Discover validated style documents without copying proprietary assets."""

    def __init__(self, directory: Path | None = None) -> None:
        configured = os.environ.get("OSTINATO_KORG_STYLE_DIRECTORY")
        self.directory = directory or (
            Path(configured) if configured else DEFAULT_IMPORTED_STYLE_DIRECTORY
        )

    def load(self) -> tuple[Style, ...]:
        """Return all valid local style documents in stable identifier order."""

        if not self.directory.exists():
            return ()
        if not self.directory.is_dir():
            raise ImportedStyleLibraryError(
                f"imported style path is not a directory: {self.directory}"
            )
        styles: list[Style] = []
        seen: set[str] = set()
        for path in sorted(self.directory.glob("*/style.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                style = style_from_dict(raw)
            except (OSError, json.JSONDecodeError, StyleDocumentError) as error:
                raise ImportedStyleLibraryError(
                    f"could not load imported style {path}: {error}"
                ) from error
            if style.id in seen:
                raise ImportedStyleLibraryError(
                    f"duplicate imported style identifier: {style.id}"
                )
            seen.add(style.id)
            styles.append(style)
        return tuple(sorted(styles, key=lambda style: style.id))
