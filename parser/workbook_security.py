"""Cheap safety checks for untrusted XLSX uploads."""

from __future__ import annotations

from io import BytesIO
from zipfile import BadZipFile, ZipFile


MAX_XLSX_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 4_096
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_MEMBER_BYTES = 50 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
REQUIRED_XLSX_MEMBERS = {"[Content_Types].xml", "xl/workbook.xml"}


class WorkbookSafetyError(ValueError):
    """Raised when an XLSX exceeds NETO's defensive upload policy."""


def validate_xlsx_archive(file_bytes: bytes) -> None:
    """Reject oversized, encrypted, malformed, or highly expanded XLSX archives."""

    if not file_bytes:
        raise WorkbookSafetyError("The uploaded XLSX is empty.")
    if len(file_bytes) > MAX_XLSX_BYTES:
        raise WorkbookSafetyError("XLSX uploads are limited to 25 MB.")

    try:
        with ZipFile(BytesIO(file_bytes)) as archive:
            entries = archive.infolist()
    except (BadZipFile, OSError, EOFError) as exc:
        raise WorkbookSafetyError("The uploaded file is not a valid XLSX archive.") from exc

    if len(entries) > MAX_ARCHIVE_ENTRIES:
        raise WorkbookSafetyError(
            f"The XLSX contains too many archive entries ({len(entries)})."
        )

    names = [entry.filename for entry in entries]
    if len(names) != len(set(names)):
        raise WorkbookSafetyError("The XLSX contains duplicate archive members.")
    if not REQUIRED_XLSX_MEMBERS.issubset(names):
        raise WorkbookSafetyError("The archive is missing required XLSX workbook files.")
    if any(entry.flag_bits & 0x1 for entry in entries):
        raise WorkbookSafetyError("Encrypted XLSX archives are not supported.")

    largest_member = max((entry.file_size for entry in entries), default=0)
    if largest_member > MAX_MEMBER_BYTES:
        raise WorkbookSafetyError(
            "An XLSX archive member exceeds the 50 MB safety limit."
        )

    uncompressed = sum(entry.file_size for entry in entries)
    if uncompressed > MAX_UNCOMPRESSED_BYTES:
        raise WorkbookSafetyError("The expanded XLSX exceeds the 100 MB safety limit.")

    compressed = sum(max(entry.compress_size, 1) for entry in entries)
    if uncompressed / max(compressed, 1) > MAX_COMPRESSION_RATIO:
        raise WorkbookSafetyError("The XLSX compression ratio exceeds the safety limit.")
