import tempfile
from pathlib import Path

import pytest

from core.ingestion import load_excel


def test_load_excel_empty_sheet_raises_clear_error():
    pytest.importorskip("openpyxl")
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmp:
        wb.save(tmp.name)
        with pytest.raises(ValueError) as excinfo:
            load_excel(Path(tmp.name))
        assert "Excel sheet is empty" in str(excinfo.value)
