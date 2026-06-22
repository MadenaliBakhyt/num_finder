"""Serper API wrapper — website search, catalog search, Instagram search."""
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
    "linkedin", "facebook", "youtube",
    "hh.kz", "hh.ru",
    "niac.kz", "safedeal.kz",
]

CATALOG_DOMAINS = ("kompra.kz", "2gis.kz", "statsnet.co", "ba.prg.kz")


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
# Scoring (for official website only)
# ---------------------------------------------------------------------------

def score_url(url: str, title: str, company_name: str) -> int:
    if not url:
        return -100
    url_low = url.lower()
    title_low = (title or "").lower()
    name = company_name.lower()

    if any(b in url_low for b in BAD_DOMAINS):
        return -100
    if any(c in url_low for c in CATALOG_DOMAINS):
        return -100
    if "instagram.com" in url_low:
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
    catalog_urls: dict[str, str] = field(default_factory=dict)
    instagram_url: Optional[str] = None
    all_results: list[dict] = field(default_factory=list)
    queries_used: int = 0


def broad_search(company_name: str, api_key: str, max_queries: int = 3) -> SearchResults:
    """Phase 1: search for website + collect catalog/instagram URLs from results."""
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

    for item in all_results:
        link = (item.get("link") or "").lower()
        for domain in CATALOG_DOMAINS:
            if domain in link and domain not in sr.catalog_urls:
                sr.catalog_urls[domain] = item["link"]
        if "instagram.com" in link and not sr.instagram_url:
            sr.instagram_url = item["link"]

    return sr


def search_catalog(company_name: str, domain: str, api_key: str) -> Optional[str]:
    name = clean_name(company_name)
    results = serper_search(f'"{name}" site:{domain}', api_key, num=3)
    for r in results:
        if domain in (r.get("link") or "").lower():
            return r["link"]
    return None


def search_instagram(company_name: str, api_key: str) -> Optional[str]:
    name = clean_name(company_name)
    results = serper_search(f'"{name}" instagram Казахстан', api_key, num=3)
    for r in results:
        if "instagram.com" in (r.get("link") or "").lower():
            return r["link"]
    return None
