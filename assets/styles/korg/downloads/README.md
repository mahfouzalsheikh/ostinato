# Download staging

1. Visit KORG's official [Arranger Bonusware](https://www.korg.com/us/features/arrangers/bonusware/)
   or [XE20 bonus styles](https://www.korg.com/caen/products/digitalpianos/xe20/bonus.php)
   page.
2. Review the package terms and download the desired ZIP files manually.
3. Save the ZIP files in this directory without renaming their contents.
4. From the repository root, run:

   ```bash
   python scripts/extract_korg_styles.py
   python scripts/inspect_korg_styles.py
   ```

Downloaded files in this directory are ignored by Git. Do not add files from
third-party style mirrors or assume that a free download is redistributable.
