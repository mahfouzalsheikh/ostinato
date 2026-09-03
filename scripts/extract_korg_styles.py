#!/usr/bin/env python3
"""Extract local official KORG style ZIP packages safely."""

from __future__ import annotations

import argparse
from pathlib import Path

from ostinato.styles.importers.korg.assets import (
    UnsafeArchiveError,
    extract_korg_archives,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace files that already exist in an extracted package",
    )
    return parser


def main() -> int:
    """Extract the repository's ignored local download staging directory."""

    arguments = build_parser().parse_args()
    repository = Path(__file__).resolve().parents[1]
    downloads = repository / "assets/styles/korg/downloads"
    extracted = repository / "assets/styles/korg/extracted"
    try:
        summaries = extract_korg_archives(
            downloads,
            extracted,
            force=arguments.force,
        )
    except (OSError, UnsafeArchiveError) as error:
        build_parser().error(str(error))
    if not summaries:
        print(f"No ZIP packages found in {downloads}")
        return 0
    for summary in summaries:
        print(summary.package)
        for extension, count in summary.extensions.items():
            print(f"  {extension}: {count}")
        print(f"  files: {summary.file_count}")
        print(f"  extracted: {summary.extracted_count}")
        print(f"  skipped existing: {summary.skipped_count}")
        print(f"  uncompressed bytes: {summary.total_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
