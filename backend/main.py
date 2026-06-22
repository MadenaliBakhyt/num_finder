"""FastAPI entry point for the company-lookup MVP."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.services.excel import (
    MAX_COMPANIES,
    build_results_workbook,
    preview_excel,
    read_company_names,
)
from backend.services.pipeline import CompanyInfo, enrich_company

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("num_finder")

BULK_WORKERS = 4

app = FastAPI(
    title="Company Lookup",
    description="Find company website, phone, email, instagram, director, activity.",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    company: str = Field(..., min_length=2, max_length=200)
    api_key: Optional[str] = None


class BulkSearchResponse(BaseModel):
    count: int
    rows: list[CompanyInfo]
    truncated: bool = False


class ExportRow(BaseModel):
    company: str
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    instagram: Optional[str] = None
    director: Optional[str] = None
    activity: Optional[str] = None


class ExportRequest(BaseModel):
    rows: list[ExportRow]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _lookup(name: str, api_key: str | None) -> CompanyInfo:
    try:
        return enrich_company(name, api_key=api_key)
    except Exception as e:
        logger.exception("lookup crashed for %r: %s", name, e)
        return CompanyInfo(company=name.strip())


@app.post("/search", response_model=CompanyInfo)
def search(req: SearchRequest) -> CompanyInfo:
    company = req.company.strip()
    if not company:
        raise HTTPException(status_code=400, detail="company must not be empty")
    logger.info("== single lookup: %s", company)
    return _lookup(company, req.api_key)


def _validate_xlsx(file: UploadFile) -> None:
    filename = (file.filename or "").lower()
    if not filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Only .xlsx/.xlsm files are supported.")


@app.post("/preview-excel")
async def preview_excel_endpoint(file: UploadFile = File(...)) -> dict:
    _validate_xlsx(file)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    try:
        preview = preview_excel(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not preview.get("total_columns"):
        raise HTTPException(status_code=400, detail="The uploaded file appears to be empty.")
    return preview


@app.post("/search-excel", response_model=BulkSearchResponse)
async def search_excel(
    file: UploadFile = File(...),
    column: int = Form(0),
    skip_first_row: bool = Form(False),
    dedupe: bool = Form(True),
    api_key: str = Form(""),
) -> BulkSearchResponse:
    _validate_xlsx(file)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        names = read_company_names(
            content, column_index=column, skip_first_row=skip_first_row, dedupe=dedupe,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not names:
        raise HTTPException(status_code=400, detail="No company names found in the selected column.")

    key = api_key or None
    logger.info("== bulk lookup: %d companies (col=%d)", len(names), column)

    def _do(name: str) -> CompanyInfo:
        return _lookup(name, key)

    with ThreadPoolExecutor(max_workers=BULK_WORKERS) as pool:
        rows = list(pool.map(_do, names))

    return BulkSearchResponse(
        count=len(rows), rows=rows, truncated=len(names) >= MAX_COMPANIES,
    )


@app.post("/export-excel")
def export_excel(req: ExportRequest) -> Response:
    if not req.rows:
        raise HTTPException(status_code=400, detail="No rows to export.")
    data = build_results_workbook([r.model_dump() for r in req.rows])
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="companies_results.xlsx"'},
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")
