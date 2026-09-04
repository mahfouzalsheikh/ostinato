#!/usr/bin/env python3
"""Stage full verified exports, preserve stable IDs, and audit every source pattern."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import replace
from pathlib import Path

from ostinato.style_timeline import imported_style_timeline
from ostinato.styles.deduplication import live_style_fingerprint
from ostinato.styles.groups import imported_style_group
from ostinato.styles.importers.korg.pa80_smf import inspect_pa80_smf_directory
from ostinato.styles.live_audio import imported_style_playback_info
from ostinato.styles.models import Style, style_from_dict, style_to_dict


def source_key(package: str | None, original: str) -> tuple[str, str]:
    return (package or "").split(" (", 1)[0].casefold(), original.casefold()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exports", type=Path)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--aliases", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(
            "output must be a new directory; existing libraries are never overwritten"
        )
    existing: dict[tuple[str, str], Style] = {}
    active_ids: set[str] = set()
    for root in (args.aliases, args.current):
        if root is None:
            continue
        for path in root.rglob("style.json"):
            style = style_from_dict(json.loads(path.read_text()))
            existing[source_key(style.source.package, style.source.original_file)] = (
                style
            )
            if root == args.current:
                active_ids.add(style.id)
    accepted: list[Style] = []
    rejected: list[dict[str, str]] = []
    missing: list[str] = []
    for directory in sorted(args.exports.iterdir()):
        manifest = directory / "complete.json"
        if not manifest.exists():
            missing.append(directory.name)
            continue
        job = json.loads(manifest.read_text())["job"]
        original = f"{Path(job['bank']).name}#{job['slot']}"
        previous = existing.get(source_key(job["package"], original))
        slug = re.sub(r"[^a-z0-9]+", "-", job["name"].casefold()).strip("-")
        identifier = previous.id if previous else f"korg-{job['id']}-{slug}"
        try:
            style = inspect_pa80_smf_directory(
                directory,
                style_name=job["name"],
                style_id=identifier,
                original_file=original,
                package=job["package"],
            ).style
            style = replace(
                style,
                metadata={
                    **style.metadata,
                    "export_scope": "all_converter_visible_chord_variations",
                    "musical_group": imported_style_group(style),
                },
            )
            named_meter = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)", style.name)
            if named_meter and style.time_signature != tuple(
                map(int, named_meter.groups())
            ):
                raise ValueError(
                    "source name's explicit meter conflicts with the converter export"
                )
            info = imported_style_playback_info(style)
            for element in style.elements:
                if element.type.value in info.sections:
                    imported_style_timeline(style, section=element.type.value)
        except (ValueError, OSError) as error:
            rejected.append(
                {"id": identifier, "name": job["name"], "reason": str(error)}
            )
            continue
        accepted.append(style)
    groups: dict[str, list[Style]] = {}
    for style in accepted:
        groups.setdefault(live_style_fingerprint(style), []).append(style)
    library: list[Style] = []
    aliases: list[dict[str, str]] = []
    args.output.mkdir(parents=True)
    for group in groups.values():
        group.sort(key=lambda style: (style.id not in active_ids, style.id))
        canonical = group[0]
        library.append(canonical)
        for style in group:
            folder = (
                args.output
                / ("library" if style is canonical else "aliases")
                / style.id
            )
            folder.mkdir(parents=True)
            (folder / "style.json").write_text(
                json.dumps(style_to_dict(style), indent=2, sort_keys=True) + "\n"
            )
            if style is not canonical:
                aliases.append({"id": style.id, "canonical": canonical.id})
    final_ids = {style.id for style in library}
    report = {
        "exported_styles": len(accepted) + len(rejected),
        "accepted_styles": len(accepted),
        "unique_styles": len(library),
        "aliases": aliases,
        "rejected": rejected,
        "missing_exports": missing,
        "previous_active_ids_absent": sorted(active_ids - final_ids),
        "restored_or_new_ids": sorted(final_ids - active_ids),
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
