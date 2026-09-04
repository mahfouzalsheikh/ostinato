"""Musical browsing categories; source package labels remain in provenance."""

from __future__ import annotations

import re

from ostinato.styles.models import Style

BUILT_IN_STYLE_GROUP = "Acoustic & Pop"
CUSTOM_STYLE_GROUP = "My styles"


def musical_style_group(name: str, package: str = "") -> str:
    """Apply editorial categories from source names, without claiming audio analysis."""
    text = re.sub(r"[^a-z0-9]", "", name.casefold())
    if "TurkishArabicWorld" in package:
        return "Arabic & Turkish"
    if any(
        word in text
        for word in (
            "tango",
            "bossa",
            "latin",
            "samba",
            "chacha",
            "salsa",
            "bolero",
            "merengue",
            "guajira",
            "mambo",
            "latquart",
        )
    ):
        return "Latin & Tango"
    if any(word in text for word in ("waltz", "walz", "class34")):
        return "Waltzes"
    if any(
        word in text
        for word in (
            "celtic",
            "jig",
            "reel",
            "armen",
            "hindi",
            "bayon",
            "stub",
            "folk",
            "polka",
        )
    ):
        return "Folk & World"
    if any(word in text for word in ("ballad", "bld", "lovetheme", "wishing")):
        return "Ballads"
    if any(
        word in text
        for word in (
            "swing",
            "jazz",
            "shearing",
            "shuffle",
            "blues",
            "orleans",
            "boogie",
            "ragtime",
        )
    ):
        return "Jazz, Swing & Blues"
    if any(word in text for word in ("funk", "soul", "motown", "gospel", "steely")):
        return "Funk & Soul"
    if any(word in text for word in ("disco", "trancy", "dance", "reggae")):
        return "Dance & Reggae"
    if any(word in text for word in ("country", "eagle", "lovinusa", "50srock")):
        return "Country & Rock 'n' Roll"
    if any(word in text for word in ("classic", "arpegg", "march", "score")):
        return "Piano & Orchestral"
    return "Acoustic & Pop"


def imported_style_group(style: Style) -> str:
    """Prefer an explicit musical category; retire old vendor/volume labels."""
    configured = style.metadata.get("musical_group")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return musical_style_group(style.name, style.source.package or "")
