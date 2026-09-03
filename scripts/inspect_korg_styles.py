#!/usr/bin/env python3
"""Inventory opaque local KORG package files without guessing their format."""

from __future__ import annotations

import argparse
from pathlib import Path

from ostinato.styles.importers.korg.assets import (
    build_style_inventory,
    write_style_inventory,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="inventory JSON path (default: local KORG asset workspace)",
    )
    return parser


def main() -> int:
    """Inspect extracted packages and write one deterministic JSON inventory."""

    arguments = build_parser().parse_args()
    repository = Path(__file__).resolve().parents[1]
    extracted = repository / "assets/styles/korg/extracted"
    output = arguments.output or repository / "assets/styles/korg/style_inventory.json"
    inventory = build_style_inventory(extracted)
    write_style_inventory(inventory, output)
    packages = inventory["packages"]
    file_count = sum(len(package["files"]) for package in packages)
    print(f"Inspected {file_count} files in {len(packages)} packages")
    for package in packages:
        for file_entry in package["files"]:
            native_probe = file_entry["native_probe"]
            if native_probe is None:
                continue
            print(
                f"{file_entry['path']}: {native_probe['format_family']} "
                f"({native_probe['support_level']})"
            )
            for index, name in enumerate(native_probe["style_names"], start=1):
                print(f"  {index}: {name}")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
