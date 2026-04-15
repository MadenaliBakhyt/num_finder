"""Company website finder using DuckDuckGo search (ddgs)."""
from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlparse

from ddgs import DDGS

logger = logging.getLogger(__name__)

# Domains that are almost never the company's official site
BAD_DOMAINS = (
    "wikipedia.org",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "hh.kz",
    "hh.ru",
    "prg.kz",
    "safedeal.kz",
    "2gis",
    "niac.kz",
    "en.nbd.ltd",
    "rusprofile.ru",
    "list-org.com",
    "kompass.com",
    "zoominfo.com",
    "bloomberg.com",
)

COMPANY_TYPE_RE = re.compile(
    r"\b(ТОО|TOO|АО|AO|JSC|LTD|LLC|ИП|ОАО|ЗАО|PLC|GMBH|INC)\b",
    flags=re.IGNORECASE,
)


def clean_name(name: str) -> str:
    """Remove anything inside brackets and extra whitespace."""
    name = re.sub(r"\(.*?\)", "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip(" \"'«»")


def remove_company_type(name: str) -> str:
    """Drop legal-form prefixes like TOO / AO / LLC for broader search."""
    return COMPANY_TYPE_RE.sub("", name).strip(" \"'«»")


def is_good_result(url: str, title: str, company_name: str) -> bool:
    """Filter out clearly-bad search results."""
    if not url:
        return False

    lowered = url.lower()
    if any(bad in lowered for bad in BAD_DOMAINS):
        return False

    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False

    if not host:
        return False

    # Prefer results where the first word of the company appears
    # in title or host. If not, still allow — ddgs top results are usually OK.
    tokens = company_name.lower().split()
    if tokens:
        name_part = tokens[0]
        if name_part in (title or "").lower() or name_part in host:
            return True

    return True


def find_company_website(company_name: str, max_results: int = 5) -> Optional[str]:
    """Return the best-guess official website URL for a company name."""
    clean = clean_name(company_name)
    alt = remove_company_type(clean)

    queries = [
        f"{clean} сайт",
        f"{alt} Kazakhstan website",
    ]

    try:
        with DDGS() as ddgs:
            for query in queries:
                logger.info("Search query: %s", query)
                try:
                    results = list(ddgs.text(query, max_results=max_results)) or []
                except Exception as e:
                    logger.warning("ddgs.text failed for %r: %s", query, e)
                    continue

                for r in results:
                    url = r.get("href") or r.get("url") or ""
                    title = r.get("title", "")
                    logger.info("  candidate: %s", url)

                    if is_good_result(url, title, clean):
                        logger.info("  ✅ selected: %s", url)
                        return url
    except Exception as e:
        logger.exception("Search failed for %r: %s", company_name, e)

    return None
