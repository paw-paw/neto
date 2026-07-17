from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from parser.workbook_security import WorkbookSafetyError, validate_xlsx_archive


ROOT = Path(__file__).resolve().parents[1]


def test_repository_workbook_passes_archive_policy() -> None:
    workbook = (
        ROOT / "tests" / "fixtures" / "cct_2026_sa3_public_schedule.xlsx"
    ).read_bytes()
    validate_xlsx_archive(workbook)


def test_high_expansion_archive_is_rejected_before_openpyxl() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/worksheets/sheet1.xml", b"0" * 1_000_000)

    with pytest.raises(WorkbookSafetyError, match="compression ratio"):
        validate_xlsx_archive(buffer.getvalue())
