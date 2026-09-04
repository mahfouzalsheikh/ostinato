from dataclasses import replace

from ostinato.styles.groups import imported_style_group, musical_style_group
from tests.unit.test_imported_style_live import _style


def test_categorizes_music_across_numbered_packages() -> None:
    style = replace(_style(), name="Blue Ballad")
    assert imported_style_group(style) == "Ballads"
    assert musical_style_group("Gtr Ballad", "Styl-v06.zip") == "Ballads"
    assert musical_style_group("Bossa Pno", "PianoSty.zip") == "Latin & Tango"


def test_uses_regional_source_category_without_vendor_label() -> None:
    style = _style()
    source = replace(style.source, package="TurkishArabicWorld.zip")
    assert imported_style_group(replace(style, source=source)) == "Arabic & Turkish"


def test_musical_override_replaces_legacy_package_group() -> None:
    style = replace(
        _style(),
        name="SweetBallad",
        metadata={"library_group": "KORG Styles · Volume 1"},
    )
    assert imported_style_group(style) == "Ballads"
    assert (
        imported_style_group(
            replace(style, metadata={"musical_group": "Wedding dances"})
        )
        == "Wedding dances"
    )
