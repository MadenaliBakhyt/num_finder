"""FastAPI entry point for the company-lookup MVP."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.services.parser import extract_phone_from_website
from backend.services.search import find_company_website

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("num_finder")

app = FastAPI(
    title="Company Lookup",
    description="Find a company's official website and phone number by name.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    company: str = Field(..., min_length=2, max_length=200)


class SearchResponse(BaseModel):
    company: str
    website: Optional[str] = None
    phone: Optional[str] = None


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    company = req.company.strip()
    if not company:
        raise HTTPException(status_code=400, detail="company must not be empty")

    logger.info("🔎 lookup: %s", company)

    try:
        website = find_company_website(company)
    except Exception as e:
        logger.exception("website lookup crashed: %s", e)
        website = None

    phone: Optional[str] = None
    if website:
        try:
            phone = extract_phone_from_website(website)
        except Exception as e:
            logger.exception("phone extraction crashed: %s", e)

    return SearchResponse(company=company, website=website, phone=phone)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount(
        "/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static"
    )

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")
