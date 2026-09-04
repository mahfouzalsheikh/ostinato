from dataclasses import replace

import pytest

from ostinato.arranger import ArrangerError, LiveArrangerService
from ostinato.styles.controls import StyleControls
from tests.unit.test_arranger import FakeArrangerAudio
from tests.unit.test_imported_style_live import expanded_style


@pytest.mark.parametrize(
    "payload",
    [
        {"role": "bass", "volume": True},
        {"role": "bass", "volume": 101},
        {"role": "bass", "muted": 1},
        {"role": "missing"},
        {"role": "bass", "unexpected": 0},
    ],
)
def test_rejects_invalid_mix_without_changing_state(payload: object) -> None:
    controls = StyleControls()
    with pytest.raises(ValueError):
        controls.update_track(payload)
    assert controls.tracks == ()


def test_backend_keeps_selections_across_status_reads_and_resets_for_new_style() -> (
    None
):
    audio = FakeArrangerAudio()
    arranger = LiveArrangerService(audio)
    style = expanded_style()
    arranger.configure_imported_styles((style, replace(style, id="korg-second")))
    arranger.command("style", style.id)
    arranger.command("variation", 4)
    arranger.command("intro_select", 2)
    arranger.command("ending_select", 2)
    arranger.command("track_mix", {"role": "bass", "volume": 60, "solo": True})
    state = arranger.snapshot()["style_controls"]
    assert isinstance(state, dict)
    assert state["variation"] == 4
    assert state["intro"] == 2
    assert state["ending"] == 2
    assert (
        audio.style_controls.track(
            next(track.role for track in audio.style_controls.tracks)
        ).volume
        == 60
    )
    with pytest.raises(ArrangerError):
        arranger.command("variation", True)
    with pytest.raises(ArrangerError):
        arranger.command("track_mix", {"role": "acc5", "muted": True})
    arranger.command("mix_reset")
    assert audio.style_controls.tracks == ()
    arranger.command("style", "korg-second")
    assert audio.style_controls == StyleControls()


def test_learned_switches_can_select_each_imported_variation() -> None:
    audio = FakeArrangerAudio()
    arranger = LiveArrangerService(audio)
    style = expanded_style()
    arranger.configure_imported_styles((style,))
    arranger.command("style", style.id)
    for action in ("variation_1", "variation_2", "variation_3", "variation_4"):
        assert arranger.trigger_performance_control(action)
    assert audio.style_controls.variation == 4
    arranger.command("style", "classic_waltz")
    assert not arranger.trigger_performance_control("variation_4")
