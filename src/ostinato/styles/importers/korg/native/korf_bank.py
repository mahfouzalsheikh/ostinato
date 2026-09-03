"""Conservative catalog probe for the observed legacy ``KORF`` style bank."""

from __future__ import annotations

from dataclasses import dataclass

_MAGIC_OFFSET = 23
_DIRECTORY_OFFSET = 36
_DIRECTORY_RECORD_SIZE = 24
_NAME_SIZE = 16
_PRIMARY_RECORD_TYPE = 2
_SECONDARY_RECORD_TYPE = 7


@dataclass(frozen=True, slots=True)
class KorfBankCatalog:
    """Display names read from a verified instance of the observed directory."""

    format_family: str
    layout: str
    support_level: str
    generation: str
    magic_offset: int
    style_names: tuple[str, ...]


def probe_korf_bank_catalog(data: bytes) -> KorfBankCatalog | None:
    """Read only the dual-record directory observed across official KORF banks.

    This deliberately does not interpret the compressed style bodies, musical
    events, sound assignments, transposition tables, or any other native field.
    Inputs that do not match every observed directory invariant stay unknown.
    """

    if (
        len(data) < _DIRECTORY_OFFSET
        or data[_MAGIC_OFFSET : _MAGIC_OFFSET + 4] != b"KORF"
    ):
        return None
    directory_size = int.from_bytes(data[32:36], "big")
    if (
        directory_size == 0
        or directory_size % _DIRECTORY_RECORD_SIZE != 0
        or _DIRECTORY_OFFSET + directory_size > len(data)
    ):
        return None

    records: dict[int, dict[int, tuple[int, str]]] = {
        _PRIMARY_RECORD_TYPE: {},
        _SECONDARY_RECORD_TYPE: {},
    }
    primary_order: list[int] = []
    versions: set[int] = set()
    for start in range(
        _DIRECTORY_OFFSET,
        _DIRECTORY_OFFSET + directory_size,
        _DIRECTORY_RECORD_SIZE,
    ):
        record = data[start : start + _DIRECTORY_RECORD_SIZE]
        record_type = record[18]
        if record_type not in records or any(
            record[position] != 0 for position in (16, 17)
        ):
            return None
        raw_name = record[:_NAME_SIZE].split(b"\0", 1)[0].rstrip(b" ")
        if any(byte < 0x20 or byte > 0x7E for byte in raw_name) or (
            record_type == _PRIMARY_RECORD_TYPE and not raw_name
        ):
            return None
        index = record[20]
        version = record[19]
        if index in records[record_type]:
            return None
        records[record_type][index] = (version, raw_name.decode("ascii"))
        if record_type == _PRIMARY_RECORD_TYPE:
            primary_order.append(index)
        versions.add(version)

    primary = records[_PRIMARY_RECORD_TYPE]
    secondary = records[_SECONDARY_RECORD_TYPE]
    indexes = list(range(len(primary)))
    if (
        not primary
        or sorted(primary) != indexes
        or (secondary and sorted(secondary) != indexes)
        or len(versions) != 1
    ):
        return None
    version = versions.pop()

    return KorfBankCatalog(
        format_family="korg_korf_style_bank",
        layout="observed_dual_record_directory",
        support_level="catalog_only",
        generation=f"directory_tag_0x{version:02x}",
        magic_offset=_MAGIC_OFFSET,
        style_names=tuple(primary[index][1] for index in primary_order),
    )
