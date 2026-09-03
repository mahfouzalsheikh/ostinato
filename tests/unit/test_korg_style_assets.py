from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from ostinato.styles.importers.korg.assets import (
    UnsafeArchiveError,
    build_style_inventory,
    extract_korg_archives,
)
from ostinato.styles.importers.korg.native import probe_korf_bank_catalog


class KorgStyleAssetTests(unittest.TestCase):
    def test_docker_context_excludes_local_korg_material(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        patterns = {
            line.strip()
            for line in (repository / ".dockerignore")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

        self.assertTrue(
            {
                "assets/styles/korg/downloads",
                "assets/styles/korg/extracted",
                "assets/styles/korg/midi",
                "assets/styles/korg/converted",
                "assets/styles/korg/style_inventory.json",
            }.issubset(patterns)
        )

        compose = (repository / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn(
            "OSTINATO_KORG_STYLE_DIRECTORY: /opt/ostinato-local-styles/korg",
            compose,
        )
        self.assertIn("source: ./assets/styles/korg/converted", compose)
        self.assertIn("target: /opt/ostinato-local-styles/korg", compose)
        self.assertIn("read_only: true", compose)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.downloads = self.root / "downloads"
        self.extracted = self.root / "extracted"
        self.downloads.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_extracts_packages_and_preserves_existing_files_without_force(self) -> None:
        archive_path = self.downloads / "Styl-v01.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("STYLE/USER01.STY", b"first")
            archive.writestr("STYLE/notes.txt", b"metadata")

        first = extract_korg_archives(self.downloads, self.extracted)
        destination = self.extracted / "Styl-v01/STYLE/USER01.STY"
        destination.write_bytes(b"local change")
        second = extract_korg_archives(self.downloads, self.extracted)
        forced = extract_korg_archives(self.downloads, self.extracted, force=True)

        self.assertEqual(first[0].extensions, {".STY": 1, ".TXT": 1})
        self.assertEqual(first[0].extracted_count, 2)
        self.assertEqual(second[0].skipped_count, 2)
        self.assertEqual(forced[0].extracted_count, 2)
        self.assertEqual(destination.read_bytes(), b"first")

    def test_rejects_archive_path_traversal_before_extracting_anything(self) -> None:
        archive_path = self.downloads / "unsafe.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("safe.STY", b"would be safe")
            archive.writestr("../escape.STY", b"escape")

        with self.assertRaisesRegex(UnsafeArchiveError, "unsafe ZIP member"):
            extract_korg_archives(self.downloads, self.extracted)

        self.assertFalse(self.extracted.exists())
        self.assertFalse((self.root / "escape.STY").exists())

    def test_inventory_reports_binary_clues_without_treating_sty_as_midi(self) -> None:
        package = self.extracted / "sample"
        package.mkdir(parents=True)
        (package / "opaque.STY").write_bytes(
            b"KORG opaque Variation 1 CV2\x00MThd\x00MTrk\xf0"
        )

        inventory = build_style_inventory(self.extracted)
        inspected = inventory["packages"][0]["files"][0]

        self.assertEqual(inspected["extension"], ".STY")
        self.assertFalse(inspected["signatures"]["starts_with_midi"])
        self.assertEqual(inspected["midi_header_offsets"], [28])
        self.assertEqual(inspected["midi_track_offsets"], [33])
        self.assertEqual(inspected["possible_sysex_offsets"], [37])
        self.assertIn("KORG opaque Variation 1 CV2", inspected["strings"])

    def test_probes_only_the_validated_observed_korf_catalog_layout(self) -> None:
        data = bytearray(36 + 16 * 24)
        data[23:27] = b"KORF"
        data[32:36] = (16 * 24).to_bytes(4, "big")
        names = tuple(f"Test Style {index + 1}" for index in range(8))
        for record_type, table_offset in ((2, 0), (7, 8)):
            for index, name in enumerate(names):
                start = 36 + (table_offset + index) * 24
                encoded = name.encode("ascii")
                data[start : start + len(encoded)] = encoded
                data[start + 18 : start + 20] = bytes((record_type, 0x11))
                data[start + 20] = index

        catalog = probe_korf_bank_catalog(bytes(data))
        corrupted = bytearray(data)
        corrupted[36 + 20] = 7

        self.assertIsNotNone(catalog)
        assert catalog is not None
        self.assertEqual(catalog.support_level, "catalog_only")
        self.assertEqual(catalog.generation, "directory_tag_0x11")
        self.assertEqual(catalog.style_names, names)
        self.assertIsNone(probe_korf_bank_catalog(bytes(corrupted)))

    def test_probes_an_observed_single_primary_directory(self) -> None:
        data = bytearray(36 + 2 * 24)
        data[23:27] = b"KORF"
        data[32:36] = (2 * 24).to_bytes(4, "big")
        for index, name in enumerate(("First", "Second")):
            start = 36 + index * 24
            data[start : start + len(name)] = name.encode("ascii")
            data[start + 18 : start + 20] = b"\x02\x11"
            data[start + 20] = index

        catalog = probe_korf_bank_catalog(bytes(data))

        self.assertIsNotNone(catalog)
        assert catalog is not None
        self.assertEqual(catalog.style_names, ("First", "Second"))

    def test_preserves_the_physical_primary_order_used_by_the_converter(self) -> None:
        data = bytearray(36 + 2 * 24)
        data[23:27] = b"KORF"
        data[32:36] = (2 * 24).to_bytes(4, "big")
        for record, (index, name) in enumerate(((1, "Second"), (0, "First"))):
            start = 36 + record * 24
            data[start : start + len(name)] = name.encode("ascii")
            data[start + 18 : start + 20] = b"\x02\x11"
            data[start + 20] = index

        catalog = probe_korf_bank_catalog(bytes(data))

        self.assertIsNotNone(catalog)
        assert catalog is not None
        self.assertEqual(catalog.style_names, ("Second", "First"))


if __name__ == "__main__":
    unittest.main()
