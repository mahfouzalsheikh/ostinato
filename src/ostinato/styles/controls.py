"""Validated performer choices for imported style sections and track mix."""

from dataclasses import dataclass, replace

from ostinato.styles.models import StyleTrackRole


@dataclass(frozen=True, slots=True)
class TrackMix:
    role: StyleTrackRole
    volume: int = 100
    muted: bool = False
    solo: bool = False


@dataclass(frozen=True, slots=True)
class StyleControls:
    variation: int = 1
    intro: int = 1
    ending: int = 1
    tracks: tuple[TrackMix, ...] = ()

    def track(self, role: StyleTrackRole) -> TrackMix:
        return next((item for item in self.tracks if item.role is role), TrackMix(role))

    def audible(self, role: StyleTrackRole) -> bool:
        track = self.track(role)
        return not track.muted and (
            not any(item.solo for item in self.tracks) or track.solo
        )

    def update_track(self, value: object) -> "StyleControls":
        if not isinstance(value, dict) or set(value) - {
            "role",
            "volume",
            "muted",
            "solo",
        }:
            raise ValueError("track mix requires role, volume, muted, or solo")
        try:
            role_value = value.get("role")
            if not isinstance(role_value, str):
                raise ValueError("track role must be a string")
            role = StyleTrackRole(role_value)
        except (ValueError, TypeError) as error:
            raise ValueError("unknown style track") from error
        old = self.track(role)
        volume = value.get("volume", old.volume)
        muted = value.get("muted", old.muted)
        solo = value.get("solo", old.solo)
        if type(volume) is not int or not 0 <= volume <= 100:
            raise ValueError("track volume must be an integer from 0 to 100")
        if type(muted) is not bool or type(solo) is not bool:
            raise ValueError("mute and solo must be boolean values")
        new = TrackMix(role, volume, muted, solo)
        return replace(
            self,
            tracks=(*(item for item in self.tracks if item.role is not role), new),
        )
