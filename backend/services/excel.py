"""Excel helpers: read company names from an uploaded file, write results."""
from __future__ import annotations

import io
import logging
from typing import Iterable

from openpyxl import Workbook, load_workbook

logger = logging.getLogger(__name__)

MAX_COMPANIES = 100  # cap to avoid runaway processing
SKIP_VALUES = {"общий итог", "итого", "total", "компания", "company", "name"}


def read_company_names(data: bytes) -> list[str]:
    """Return a de-duplicated list of company names from the first column
    of the uploaded xlsx file.

    Tolerant of header rows and blanks. Any cell whose lowercased value is in
    ``SKIP_VALUES`` is skipped.
    """
    try:
        wb = load_workbook(filename=io.BytesIO(data), data_only=True, read_only=True)
    except Exception as e:
        raise ValueError(f"Could not read Excel file: {e}") from e

    ws = wb.active
    if ws is None:
        return []

    seen: set[str] = set()
    names: list[str] = []

    for row in ws.iter_rows(min_col=1, max_col=1, values_only=True):
        if not row:
            continue
        value = row[0]
        if value is None:
            continue

        name = str(value).strip()
        if not name:
            continue
        if name.lower() in SKIP_VALUES:
            continue

        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)

        if len(names) >= MAX_COMPANIES:
            logger.info("hit MAX_COMPANIES=%d, truncating input", MAX_COMPANIES)
            break

    return names


def build_results_workbook(rows: Iterable[dict]) -> bytes:
    """Serialize result rows to an xlsx byte blob."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Results"
    ws.append(["Company", "Website", "Phone"])

    for r in rows:
        ws.append([
            r.get("company") or "",
            r.get("website") or "",
            r.get("phone") or "",
        ])

    # Widen columns for readability
    widths = {"A": 40, "B": 45, "C": 30}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
