"""Enrichment pipeline — orchestrates multi-source data collection."""
from __future__ import annotations

import logging
import re
from typing import Optional

from pydantic import BaseModel

from backend.services.parser import (
    PageData,
    extract_from_snippets,
    parse_catalog_page,
    parse_company_website,
)
from backend.services.search import (
    broad_search,
    search_catalog,
    search_instagram,
)

logger = logging.getLogger(__name__)

MAX_QUERIES = 7

CATALOG_SEARCH_ORDER = ["kompra.kz", "2gis.kz", "statsnet.co", "ba.prg.kz"]

_IG_RE = re.compile(r"instagram\.com/([a-zA-Z0-9_.]+)")


class CompanyInfo(BaseModel):
    company: str
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    instagram: Optional[str] = None
    director: Optional[str] = None
    activity: Optional[str] = None


def _ig_from_url(url: str | None) -> Optional[str]:
    if not url:
        return None
    m = _IG_RE.search(url)
    return f"@{m.group(1)}" if m else None


def _still_missing(info: CompanyInfo) -> bool:
    return not (info.phone and info.director and info.activity)


def enrich_company(company_name: str, api_key: str | None = None) -> CompanyInfo:
    info = CompanyInfo(company=company_name.strip())
    if not api_key:
        logger.error("No API key — skipping %s", company_name)
        return info

    all_phones: list[str] = []
    all_emails: list[str] = []
    all_ig: list[str] = []
    director: Optional[str] = None
    activity: Optional[str] = None

    # ── Phase 1: broad search (up to 3 Serper queries) ──────────────
    sr = broad_search(company_name, api_key, max_queries=3)
    budget = MAX_QUERIES - sr.queries_used

    info.website = sr.website

    if sr.instagram_url:
        ig = _ig_from_url(sr.instagram_url)
        if ig:
            all_ig.append(ig)

    # ── Phase 2: parse company website ──────────────────────────────
    if info.website:
        logger.info("  parse website: %s", info.website)
        wd = parse_company_website(info.website)
        all_phones.extend(wd.phones)
        all_emails.extend(wd.emails)
        all_ig.extend(wd.instagrams)

    # ── Phase 3: snippets (free) ────────────────────────────────────
    sd = extract_from_snippets(sr.all_results)
    all_phones.extend(sd.phones)
    all_emails.extend(sd.emails)

    # ── Phase 4: catalog search + parse ─────────────────────────────
    catalog_urls = dict(sr.catalog_urls)

    for domain in CATALOG_SEARCH_ORDER:
        if budget <= 0:
            break
        if domain in catalog_urls:
            continue
        if not _still_missing(info):
            break
        logger.info("  serper catalog: %s", domain)
        url = search_catalog(company_name, domain, api_key)
        budget -= 1
        if url:
            catalog_urls[domain] = url

    for domain, url in catalog_urls.items():
        logger.info("  parse catalog %s: %s", domain, url)
        try:
            cd = parse_catalog_page(url)
        except Exception as e:
            logger.warning("  catalog parse failed %s: %s", url, e)
            continue
        all_phones.extend(cd.phones)
        all_emails.extend(cd.emails)
        if not director and cd.director:
            director = cd.director
        if not activity and cd.activity:
            activity = cd.activity

    # ── Phase 5: Instagram search ───────────────────────────────────
    if not all_ig and budget > 0:
        logger.info("  serper instagram")
        ig_url = search_instagram(company_name, api_key)
        budget -= 1
        ig = _ig_from_url(ig_url)
        if ig:
            all_ig.append(ig)

    # ── Build final result ──────────────────────────────────────────
    phones = list(dict.fromkeys(all_phones))[:5]
    emails = list(dict.fromkeys(all_emails))[:3]
    instagrams = list(dict.fromkeys(all_ig))

    info.phone = ", ".join(phones) or None
    info.email = ", ".join(emails) or None
    info.instagram = instagrams[0] if instagrams else None
    info.director = director
    info.activity = activity

    logger.info(
        "  DONE %s  web=%s  phones=%d  emails=%d  ig=%s  dir=%s",
        company_name,
        bool(info.website),
        len(phones),
        len(emails),
        bool(info.instagram),
        bool(info.director),
    )
    return info
