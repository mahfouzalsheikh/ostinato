#!/usr/bin/env python3
"""Report exact duplicates in the host-local KORG live-style library."""

from __future__ import annotations

import argparse
from pathlib import Path

from ostinato.styles.deduplication import (
    duplicate_live_style_groups,
    live_style_fingerprint,
)
from ostinato.styles.library import ImportedStyleLibrary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path)
    parser.add_argument("--fail-on-duplicates", action="store_true")
    arguments = parser.parse_args()

    styles = ImportedStyleLibrary(arguments.directory).load()
    groups = duplicate_live_style_groups(styles)
    print(f"Audited {len(styles)} styles; {len(groups)} duplicate group(s)")
    for group in groups:
        print(f"  SHA-256 {live_style_fingerprint(group[0])}")
        for style in group:
            package = style.source.package or "unlabeled package"
            print(f"    {style.id}: {style.name} · {package}")
    return 1 if groups and arguments.fail_on_duplicates else 0


if __name__ == "__main__":
    raise SystemExit(main())
