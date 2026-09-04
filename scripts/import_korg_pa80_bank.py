#!/usr/bin/env python3
"""Import all available section exports from one catalogued KORG bank."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from ostinato.style_timeline import imported_style_timeline
from ostinato.styles.importers.korg.midi_style_importer import (
    UnsupportedKorgStyleFormat,
)
from ostinato.styles.importers.korg.native import probe_korf_bank_catalog
from ostinato.styles.importers.korg.pa80_smf import inspect_pa80_smf_directory
from ostinato.styles.live_audio import (
    imported_style_playback_info,
    imported_style_rhythm_spans,
)
from ostinato.styles.models import style_to_dict

_EXPECTED_FILES = {"v1cv1.mid", "i1cv1.mid", "f1cv1.mid", "f2cv1.mid", "e1cv1.mid"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bank", type=Path, help="original .STY bank")
    parser.add_argument("midi", type=Path, help="directory of numbered export folders")
    parser.add_argument("--bank-id", required=True, help="lowercase stable bank slug")
    parser.add_argument("--package", required=True, help="source package label")
    parser.add_argument("--group", required=True, help="arranger group label")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", arguments.bank_id) is None:
        build_parser().error("--bank-id must be a lowercase slug")
    catalog = probe_korf_bank_catalog(arguments.bank.read_bytes())
    if catalog is None:
        build_parser().error("bank does not expose the validated legacy KORF catalog")

    imported = 0
    rejected = 0
    missing = 0
    for index, name in enumerate(catalog.style_names, start=1):
        midi_directory = arguments.midi / f"{index:03d}"
        files = (
            {path.name for path in midi_directory.glob("*.mid")}
            if midi_directory.is_dir()
            else set()
        )
        if not _EXPECTED_FILES.issubset(files):
            print(
                f"MISSING {index:03d} {name}: complete five-section export unavailable"
            )
            missing += 1
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "style"
        style_id = f"korg-{arguments.bank_id}-{slug}"
        try:
            result = inspect_pa80_smf_directory(
                midi_directory,
                style_name=name,
                original_file=f"{arguments.bank.name}#{index}",
                package=arguments.package,
                style_id=style_id,
                library_group=arguments.group,
            )
            style = result.style
            imported_style_playback_info(style)
            imported_style_rhythm_spans(style)
            imported_style_timeline(style)
        except (OSError, UnsupportedKorgStyleFormat, ValueError) as error:
            print(f"REJECTED {index:03d} {name}: {error}")
            rejected += 1
            continue

        output_directory = arguments.output / style.id
        if output_directory.exists():
            build_parser().error(f"refusing to overwrite {output_directory}")
        output_directory.mkdir(parents=True)
        (output_directory / "style.json").write_text(
            json.dumps(style_to_dict(style), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"IMPORTED {index:03d} {name}: {style.id}")
        imported += 1

    print(f"SUMMARY imported={imported} rejected={rejected} missing={missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
