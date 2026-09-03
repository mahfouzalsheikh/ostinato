from dataclasses import replace

from ostinato.styles.groups import imported_style_group
from tests.unit.test_imported_style_live import _style


def test_groups_numbered_official_volumes_naturally() -> None:
    style = _style()
    source = replace(style.source, package="Styles - vol. 23.zip")

    assert imported_style_group(replace(style, source=source)) == (
        "KORG Styles · Volume 23"
    )


def test_groups_known_named_library() -> None:
    style = _style()
    source = replace(
        style.source,
        package="TurkishArabicWorld.zip (official KORG Bonusware)",
    )

    assert imported_style_group(replace(style, source=source)) == (
        "KORG · Turkish Arabic World"
    )


def test_explicit_group_metadata_takes_priority() -> None:
    style = replace(_style(), metadata={"library_group": "KORG · Curated"})

    assert imported_style_group(style) == "KORG · Curated"
