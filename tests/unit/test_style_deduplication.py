from dataclasses import replace

from ostinato.styles.deduplication import duplicate_live_style_groups
from ostinato.styles.models import NoteEvent
from tests.unit.test_imported_style_live import _style


def test_finds_identity_independent_exact_live_duplicate() -> None:
    original = _style()
    alias = replace(original, id="korg-alias", name="Alias")

    assert duplicate_live_style_groups((original, alias)) == ((original, alias),)


def test_distinguishes_one_changed_live_note() -> None:
    original = _style()
    element = original.elements[0]
    variation = element.chord_variations[0]
    track = variation.tracks[0]
    events = tuple(
        replace(event, note=event.note + 1) if isinstance(event, NoteEvent) else event
        for event in track.events
    )
    changed = replace(
        original,
        id="korg-changed",
        elements=(
            replace(
                element,
                chord_variations=(
                    replace(
                        variation,
                        tracks=(replace(track, events=events), *variation.tracks[1:]),
                    ),
                ),
            ),
            *original.elements[1:],
        ),
    )

    assert duplicate_live_style_groups((original, changed)) == ()


def test_preserves_aliases_that_differ_only_in_a_later_variation() -> None:
    from tests.unit.test_imported_style_live import expanded_style

    original = expanded_style()
    extra = original.elements[-1]
    changed = replace(original, id="korg-extra", elements=original.elements[:-1])
    assert extra.type.value == "ending_2"
    assert duplicate_live_style_groups((original, changed)) == ()


def test_preserves_different_higher_chord_patterns() -> None:
    original = _style()
    first = original.elements[0]
    extra = replace(first.chord_variations[0], number=2)
    changed = replace(
        original,
        id="korg-cv2",
        elements=(
            replace(first, chord_variations=(*first.chord_variations, extra)),
            *original.elements[1:],
        ),
    )
    assert duplicate_live_style_groups((original, changed)) == ()
