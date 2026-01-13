import tempfile
from pathlib import Path

import pytest

from core.ingestion import (
    detect_useful_columns,
    estimate_duration_minutes,
    infer_category,
    load_csv,
    load_excel,
    normalize_rows,
)


def test_detect_and_normalize_csv(tmp_path: Path):
    csv_path = tmp_path / "tasks.csv"
    csv_path.write_text(
        "Task Name,Category label,Time (h)\n" " Nettoyage   données ,Data Cleanup,1.5h\n" "Rapport final , , \n",
        encoding="utf-8",
    )

    rows = load_csv(csv_path)
    detected = detect_useful_columns(rows[0].keys())
    assert detected.text == "Task Name"
    assert detected.category == "Category label"
    assert detected.duration == "Time (h)"

    normalized = normalize_rows(rows)
    assert normalized[0]["title"] == "Nettoyage données"
    assert normalized[0]["category"] == "Data Cleanup"
    assert normalized[0]["estimated_minutes"] == 90
    # missing category falls back to text-based inference
    assert normalized[1]["category"] == "reporting"
    # missing duration falls back to heuristic
    assert normalized[1]["estimated_minutes"] == 60


def test_excel_import_and_duration_parsing(tmp_path: Path):
    try:
        from openpyxl import Workbook
    except ImportError:  # pragma: no cover - handled by requirement install
        pytest.skip("openpyxl not installed")

    wb = Workbook()
    ws = wb.active
    ws.title = "Raw"
    ws.append(["Description", "Hours estimate"])
    ws.append(["Analyse sécurité", "2h"])
    ws.append(["Data quality sweep", "45m"])
    excel_path = tmp_path / "tasks.xlsx"
    wb.save(excel_path)

    rows = load_excel(excel_path, sheet_name="Raw")
    normalized = normalize_rows(rows)

    assert normalized[0]["category"] == "security"
    assert normalized[0]["estimated_minutes"] == 120
    assert normalized[1]["category"] == "data quality"
    assert normalized[1]["estimated_minutes"] == 45


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("30m", 30),
        ("1h", 60),
        ("2 hours", 120),
        ("1.5d", 720),
        (None, 60),
    ],
)
def test_estimation_rules(raw, expected):
    assert estimate_duration_minutes(raw, "short task for estimation") == expected


def test_category_inference_from_text():
    assert infer_category("", "Prepare finance report and consolidate") == "finance"
    assert infer_category("", "Implement new security controls") == "security"
    assert infer_category("custom", "Does not matter") == "custom"
