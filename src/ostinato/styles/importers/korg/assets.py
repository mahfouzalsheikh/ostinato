"""Local-only KORG package extraction and format-neutral binary inventory."""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import stat
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ostinato.styles.importers.korg.native import probe_korf_bank_catalog

_ASCII_RUN = re.compile(rb"[\x20-\x7e]{4,}")
_STYLE_WORD = re.compile(
    r"\b(?:intro|variation|var|fill|break|ending|end|cv\s*\d+)\b",
    re.IGNORECASE,
)
_MAX_REPORTED_OFFSETS = 1_000
_MAX_REPORTED_STRINGS = 200
_MAX_STRING_LENGTH = 160


class UnsafeArchiveError(ValueError):
    """Raised when a ZIP member could escape or link outside its package."""


@dataclass(frozen=True, slots=True)
class ArchiveSummary:
    """Extraction result for one local ZIP package."""

    package: str
    file_count: int
    extracted_count: int
    skipped_count: int
    extensions: dict[str, int]
    total_size: int


def extract_korg_archives(
    downloads_root: Path,
    extracted_root: Path,
    *,
    force: bool = False,
) -> tuple[ArchiveSummary, ...]:
    """Safely extract each ZIP without silently replacing existing files."""

    summaries: list[ArchiveSummary] = []
    for archive_path in sorted(
        downloads_root.glob("*.zip"), key=lambda path: path.name
    ):
        package_root = extracted_root / archive_path.stem
        with zipfile.ZipFile(archive_path) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            for member in members:
                _validated_member_path(member)

            extracted_count = 0
            skipped_count = 0
            extensions: Counter[str] = Counter()
            total_size = 0
            for member in members:
                relative_path = _validated_member_path(member)
                destination = package_root.joinpath(*relative_path.parts)
                extension = destination.suffix.upper() or "<none>"
                extensions[extension] += 1
                total_size += member.file_size
                if destination.exists() and not force:
                    skipped_count += 1
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                _extract_member_atomically(archive, member, destination)
                extracted_count += 1

        summaries.append(
            ArchiveSummary(
                package=archive_path.stem,
                file_count=len(members),
                extracted_count=extracted_count,
                skipped_count=skipped_count,
                extensions=dict(sorted(extensions.items())),
                total_size=total_size,
            )
        )
    return tuple(summaries)


def build_style_inventory(extracted_root: Path) -> dict[str, Any]:
    """Inspect extracted files without assigning proprietary format semantics."""

    packages: list[dict[str, Any]] = []
    if not extracted_root.exists():
        return {"version": 1, "packages": packages}
    package_paths = sorted(
        (path for path in extracted_root.iterdir() if path.is_dir()),
        key=lambda path: path.name.casefold(),
    )
    for package_path in package_paths:
        files = [
            inspect_style_file(path, relative_to=extracted_root)
            for path in sorted(
                (
                    candidate
                    for candidate in package_path.rglob("*")
                    if candidate.is_file()
                ),
                key=lambda path: path.as_posix().casefold(),
            )
        ]
        packages.append({"name": package_path.name, "files": files})
    return {"version": 1, "packages": packages}


def inspect_style_file(path: Path, *, relative_to: Path) -> dict[str, Any]:
    """Collect bounded structural clues from one opaque local file."""

    data = path.read_bytes()
    strings = [
        match.group().decode("ascii")[:_MAX_STRING_LENGTH]
        for match in _ASCII_RUN.finditer(data)
    ]
    strings_truncated = len(strings) > _MAX_REPORTED_STRINGS
    strings = strings[:_MAX_REPORTED_STRINGS]
    midi_header_offsets, midi_headers_truncated = _offsets(data, b"MThd")
    midi_track_offsets, midi_tracks_truncated = _offsets(data, b"MTrk")
    riff_offsets, riff_offsets_truncated = _offsets(data, b"RIFF")
    zip_offsets, zip_offsets_truncated = _offsets(data, b"PK\x03\x04")
    sysex_offsets, sysex_truncated = _offsets(data, b"\xf0")
    native_catalog = probe_korf_bank_catalog(data)
    return {
        "path": path.relative_to(relative_to).as_posix(),
        "filename": path.name,
        "extension": path.suffix.upper(),
        "size": len(data),
        "header_hex": data[:32].hex(" "),
        "entropy_bits_per_byte": round(_entropy(data), 6),
        "signatures": {
            "starts_with_midi": data.startswith(b"MThd"),
            "starts_with_riff": data.startswith(b"RIFF"),
            "starts_with_zip": data.startswith((b"PK\x03\x04", b"PK\x05\x06")),
        },
        "midi_header_offsets": midi_header_offsets,
        "midi_header_offsets_truncated": midi_headers_truncated,
        "midi_track_offsets": midi_track_offsets,
        "midi_track_offsets_truncated": midi_tracks_truncated,
        "riff_header_offsets": riff_offsets,
        "riff_header_offsets_truncated": riff_offsets_truncated,
        "zip_header_offsets": zip_offsets,
        "zip_header_offsets_truncated": zip_offsets_truncated,
        "possible_sysex_offsets": sysex_offsets,
        "possible_sysex_offsets_truncated": sysex_truncated,
        "strings": strings,
        "strings_truncated": strings_truncated,
        "possible_style_markers": [
            value for value in strings if _STYLE_WORD.search(value) is not None
        ],
        "native_probe": (
            {
                "format_family": native_catalog.format_family,
                "layout": native_catalog.layout,
                "support_level": native_catalog.support_level,
                "generation": native_catalog.generation,
                "magic_offset": native_catalog.magic_offset,
                "style_count": len(native_catalog.style_names),
                "style_names": list(native_catalog.style_names),
            }
            if native_catalog is not None
            else None
        ),
    }


def write_style_inventory(inventory: dict[str, Any], output_path: Path) -> None:
    """Atomically write deterministic, readable inventory JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            json.dump(inventory, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
        os.replace(temporary_name, output_path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _validated_member_path(member: zipfile.ZipInfo) -> PurePosixPath:
    name = member.filename
    path = PurePosixPath(name)
    unix_mode = member.external_attr >> 16
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or stat.S_ISLNK(unix_mode)
        or member.flag_bits & 0x1
    ):
        raise UnsafeArchiveError(f"unsafe ZIP member: {name!r}")
    return path


def _extract_member_atomically(
    archive: zipfile.ZipFile,
    member: zipfile.ZipInfo,
    destination: Path,
) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    try:
        with archive.open(member) as source, os.fdopen(descriptor, "wb") as target:
            shutil.copyfileobj(source, target)
        os.replace(temporary_name, destination)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _offsets(data: bytes, needle: bytes) -> tuple[list[int], bool]:
    offsets: list[int] = []
    start = 0
    while len(offsets) <= _MAX_REPORTED_OFFSETS:
        offset = data.find(needle, start)
        if offset < 0:
            break
        offsets.append(offset)
        start = offset + 1
    return offsets[:_MAX_REPORTED_OFFSETS], len(offsets) > _MAX_REPORTED_OFFSETS


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    return -sum(
        (count / length) * math.log2(count / length) for count in counts.values()
    )
