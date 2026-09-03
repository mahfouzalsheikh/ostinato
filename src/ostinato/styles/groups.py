"""Stable display groups for built-in, custom, and imported arranger styles."""

from __future__ import annotations

import re
from pathlib import Path

from ostinato.styles.models import Style

BUILT_IN_STYLE_GROUP = "Built-in styles"
CUSTOM_STYLE_GROUP = "My styles"
_VOLUME_PACKAGE = re.compile(
    r"^(?:Styl-v|Styles\s*-\s*vol\.?\s*)(?P<number>\d+)", re.IGNORECASE
)
_KNOWN_PACKAGES = {
    "PianoSty": "KORG · Piano Styles",
    "RealDrums": "KORG · Real Drums",
    "TurkishArabicWorld": "KORG · Turkish Arabic World",
    "Mexican_Styles": "KORG · Mexican Styles",
}


def imported_style_group(style: Style) -> str:
    """Return a readable group without inferring musical genre from style data."""

    configured = style.metadata.get("library_group")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()

    package = style.source.package
    if package is None:
        return "KORG · Other imports"
    package_name = package.split(" (", 1)[0]
    stem = Path(package_name).stem
    volume = _VOLUME_PACKAGE.match(stem)
    if volume is not None:
        return f"KORG Styles · Volume {int(volume.group('number'))}"
    return _KNOWN_PACKAGES.get(stem, f"KORG · {stem.replace('_', ' ')}")
