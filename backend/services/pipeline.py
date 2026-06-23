"""Enrichment pipeline — company website + ba.prg.kz data collection."""
from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel

from backend.services.parser import (
    extract_from_snippets,
    parse_baprg_page,
    parse_company_website,
)
from backend.services.search import broad_search, search_baprg

logger = logging.getLogger(__name__)


class CompanyInfo(BaseModel):
    company: str
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    instagram: Optional[str] = None
    director: Optional[str] = None
    activity: Optional[str] = None


def enrich_company(company_name: str, api_key: str | None = None) -> CompanyInfo:
    info = CompanyInfo(company=company_name.strip())
    if not api_key:
        logger.error("No API key — skipping %s", company_name)
        return info

    all_phones: list[str] = []
    all_emails: list[str] = []

    # ── Phase 1: Serper broad search (up to 3 queries) ──────────────
    sr = broad_search(company_name, api_key, max_queries=3)
    info.website = sr.website

    # ── Phase 2: parse company website ──────────────────────────────
    if info.website:
        logger.info("  parse website: %s", info.website)
        wd = parse_company_website(info.website)
        all_phones.extend(wd.phones)
        all_emails.extend(wd.emails)
        if wd.instagrams:
            info.instagram = wd.instagrams[0]

    # ── Phase 3: extract from Serper snippets (free) ────────────────
    sd = extract_from_snippets(sr.all_results)
    all_phones.extend(sd.phones)
    all_emails.extend(sd.emails)

    # ── Phase 4: ba.prg.kz — director, activity, contacts ──────────
    baprg_url = sr.baprg_url
    if not baprg_url:
        logger.info("  serper: searching ba.prg.kz")
        baprg_url = search_baprg(company_name, api_key)

    if baprg_url:
        logger.info("  parse ba.prg.kz: %s", baprg_url)
        try:
            bd = parse_baprg_page(baprg_url)
            info.director = bd.director
            info.activity = bd.activity
            all_phones.extend(bd.phones)
            all_emails.extend(bd.emails)

            # Use ba.prg.kz website as fallback if we didn't find one via Serper
            if not info.website and bd.website:
                info.website = bd.website
                # Also try to parse that site for contacts
                logger.info("  parse website (from ba.prg): %s", bd.website)
                wd2 = parse_company_website(bd.website)
                all_phones.extend(wd2.phones)
                all_emails.extend(wd2.emails)
                if not info.instagram and wd2.instagrams:
                    info.instagram = wd2.instagrams[0]
        except Exception as e:
            logger.warning("  ba.prg.kz parse failed: %s", e)

    # ── Build final result ──────────────────────────────────────────
    phones = list(dict.fromkeys(all_phones))[:5]
    emails = list(dict.fromkeys(all_emails))[:3]

    info.phone = ", ".join(phones) or None
    info.email = ", ".join(emails) or None

    logger.info(
        "  DONE %s  web=%s  ph=%d  em=%d  ig=%s  dir=%s  act=%s",
        company_name,
        bool(info.website),
        len(phones),
        len(emails),
        bool(info.instagram),
        bool(info.director),
        bool(info.activity),
    )
    return info
