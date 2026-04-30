"""Company website finder using Google Serper API."""
from __future__ import annotations

import logging
import os
import random
import re
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

SERPER_URL = "https://google.serper.dev/search"

_session = requests.Session()

BAD_DOMAINS = [
    "wikipedia", "wikimedia.org",
    "linkedin", "facebook", "instagram", "youtube",
    "hh.kz", "hh.ru",
    "niac.kz", "kompra.kz", "safedeal.kz",
    "2gis", "statsnet",
    "pk.uchet.kz", "kyc.kz", "kgd.gov.kz",
]


def clean_name(name: str) -> str:
    return re.sub(r"\(.*?\)", "", str(name)).strip()


def score_url(url: str, title: str, company_name: str) -> int:
    if not url:
        return -100

    url_low = url.lower()
    title_low = (title or "").lower()
    name = company_name.lower()

    if any(b in url_low for b in BAD_DOMAINS):
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


def _pick_best(results: list[dict], company: str) -> Optional[str]:
    best = None
    best_score = -999

    for item in results:
        url = item.get("link")
        title = item.get("title", "")
        s = score_url(url, title, company)
        if s > best_score:
            best_score = s
            best = url

    return best if best_score >= 1 else None


def find_company_website(
    company_name: str,
    api_key: str | None = None,
) -> Optional[str]:
    key = api_key or os.environ.get("SERPER_API_KEY", "")
    if not key:
        logger.error("SERPER_API_KEY is not set — cannot search")
        return None

    try:
        name = clean_name(company_name)
        queries = [
            f"{name} официальный сайт Казахстан",
            f"{name} site:.kz",
            f"{name} company official website",
        ]

        headers = {
            "X-API-KEY": key,
            "Content-Type": "application/json",
        }

        for query in queries:
            logger.info("Serper query: %s", query)

            payload = {"q": query, "gl": "kz", "hl": "ru", "num": 5}
            time.sleep(random.uniform(0.3, 0.7))

            try:
                resp = _session.post(
                    SERPER_URL, json=payload, headers=headers, timeout=10,
                )
            except requests.RequestException as e:
                logger.warning("Serper request failed: %s", e)
                continue

            if resp.status_code != 200:
                logger.warning("Serper HTTP %d: %s", resp.status_code, resp.text[:200])
                continue

            results = resp.json().get("organic", [])
            if results:
                best = _pick_best(results, company_name)
                if best:
                    logger.info("  selected: %s", best)
                    return best

    except Exception as e:
        logger.exception("Search failed for %r: %s", company_name, e)

    return None
