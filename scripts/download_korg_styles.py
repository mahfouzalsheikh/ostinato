#!/usr/bin/env python3
"""Print the approved official KORG catalogs and local download workflow."""

from __future__ import annotations

from pathlib import Path

SOURCES = (
    (
        "KORG Arranger Bonusware",
        "https://www.korg.com/us/features/arrangers/bonusware/",
    ),
    (
        "KORG XE20 bonus styles",
        "https://www.korg.com/caen/products/digitalpianos/xe20/bonus.php",
    ),
)


def main() -> int:
    """Show source pages without scraping or guessing mutable package URLs."""

    repository = Path(__file__).resolve().parents[1]
    destination = repository / "assets/styles/korg/downloads"
    print("Approved official KORG style catalogs:")
    for name, url in SOURCES:
        print(f"  {name}: {url}")
    print(f"\nDownload ZIP packages manually into:\n  {destination}")
    print("\nThen run:\n  python scripts/extract_korg_styles.py")
    print("  python scripts/inspect_korg_styles.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
