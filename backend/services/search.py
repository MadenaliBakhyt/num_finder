"""Serper API wrapper — website search, ba.prg.kz lookup, Instagram."""
from __future__ import annotations

import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

SERPER_URL = "https://google.serper.dev/search"
_session = requests.Session()

BAD_DOMAINS = [
    "wikipedia", "wikimedia.org",
    "linkedin", "facebook", "youtube", "twitter.com", "x.com",
    "hh.kz", "hh.ru",
    "niac.kz", "safedeal.kz",
    "kompra.kz", "statsnet.co",
    "2gis", "flamp.kz",
    "prg.kz", "ba.prg.kz",
    "cdb.kz",
    "opnbk.kz",
    ".gov.kz",
    "rusprofile.ru", "list-org.com",
    "zoominfo.com", "bloomberg.com",
    "kompass.com", "en.nbd.ltd",
]


def clean_name(name: str) -> str:
    return re.sub(r"\(.*?\)", "", str(name)).strip()


# ---------------------------------------------------------------------------
# Low-level Serper call
# ---------------------------------------------------------------------------

def serper_search(query: str, api_key: str, num: int = 5) -> list[dict]:
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"q": query, "gl": "kz", "hl": "ru", "num": num}

    time.sleep(random.uniform(0.3, 0.7))
    try:
        resp = _session.post(SERPER_URL, json=payload, headers=headers, timeout=10)
    except requests.RequestException as e:
        logger.warning("Serper request failed: %s", e)
        return []
    if resp.status_code != 200:
        logger.warning("Serper HTTP %d: %s", resp.status_code, resp.text[:200])
        return []
    return resp.json().get("organic", [])


# ---------------------------------------------------------------------------
# Scoring — for the company's OWN website only
# ---------------------------------------------------------------------------

def score_url(url: str, title: str, company_name: str) -> int:
    if not url:
        return -100
    url_low = url.lower()
    title_low = (title or "").lower()
    name = company_name.lower()

    if any(b in url_low for b in BAD_DOMAINS):
        return -100
    if "instagram.com" in url_low:
        return -100
    # Reject URLs that look like registry/API pages
    if "/registry/" in url_low or "/api/" in url_low or "/sistema/" in url_low:
        return -100

    score = 0
    name_key = re.sub(r"[^a-zA-Zа-яА-Я]", "", name)[:6]
    if name_key and name_key in url_low:
        score += 5
    if name_key and name_key in title_low:
        score += 3
    if ".kz" in url_low:
        score += 2
    domain = url_low.split("//")[-1].split("/")[0]
    if len(domain) < 25:
        score += 1
    return score


def _pick_best_website(results: list[dict], company: str) -> Optional[str]:
    best, best_score = None, -999
    for item in results:
        s = score_url(item.get("link", ""), item.get("title", ""), company)
        if s > best_score:
            best_score = s
            best = item.get("link")
    return best if best_score >= 1 else None


# ---------------------------------------------------------------------------
# Structured search result
# ---------------------------------------------------------------------------

@dataclass
class SearchResults:
    website: Optional[str] = None
    baprg_url: Optional[str] = None
    all_results: list[dict] = field(default_factory=list)
    queries_used: int = 0


def broad_search(company_name: str, api_key: str, max_queries: int = 3) -> SearchResults:
    """Search for company website + collect ba.prg.kz URL from results."""
    name = clean_name(company_name)
    queries = [
        f"{name} официальный сайт Казахстан",
        f"{name} site:.kz",
        f"{name} company official website",
    ]

    sr = SearchResults()
    all_results: list[dict] = []

    for query in queries[:max_queries]:
        logger.info("  serper: %s", query)
        results = serper_search(query, api_key)
        sr.queries_used += 1
        all_results.extend(results)

        website = _pick_best_website(all_results, company_name)
        if website:
            sr.website = website
            break

    if not sr.website:
        sr.website = _pick_best_website(all_results, company_name)

    sr.all_results = all_results

    # Collect ba.prg.kz URL from the organic results
    for item in all_results:
        link = (item.get("link") or "").lower()
        if "ba.prg.kz" in link and not sr.baprg_url:
            sr.baprg_url = item["link"]
            break

    return sr


def search_baprg(company_name: str, api_key: str) -> Optional[str]:
    """Targeted search for this company on ba.prg.kz."""
    name = clean_name(company_name)
    results = serper_search(f'"{name}" site:ba.prg.kz', api_key, num=3)
    for r in results:
        if "ba.prg.kz" in (r.get("link") or "").lower():
            return r["link"]
    return None
