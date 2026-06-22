"""Page scrapers — extract phones, emails, instagram, director, activity."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_session = requests.Session()
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru,en;q=0.9,kk;q=0.8",
}
_TIMEOUT = 8

RAW_PHONE_RE = re.compile(r"\+?\d[\d\s\-\(\)]{8,}")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
INSTAGRAM_RE = re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)/?")

_DIRECTOR_PATTERNS = [
    re.compile(
        r"(?:Первый руководитель|Руководитель|Директор|Ген\.?\s*директор)"
        r"[:\s]+([А-ЯЁA-Z][а-яёa-z]+\s+[А-ЯЁA-Z][а-яёa-z]+(?:\s+[А-ЯЁA-Z][а-яёa-z]+)?)"
    ),
]

_ACTIVITY_PATTERNS = [
    re.compile(
        r"(?:Основной вид деятельности|Вид деятельности|ОКЭД|Деятельность)"
        r"[:\s]+(.+?)(?:\n|$|\.\s)"
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch(url: str) -> Optional[str]:
    try:
        r = _session.get(url, timeout=_TIMEOUT, headers=_HEADERS, allow_redirects=True)
        if r.status_code != 200:
            return None
        ct = r.headers.get("Content-Type", "")
        if "html" not in ct and "text" not in ct:
            return None
        return r.text
    except Exception:
        return None


def clean_phones(raw: list[str]) -> list[str]:
    out: list[str] = []
    for p in raw:
        digits = re.sub(r"\D", "", p)
        if len(digits) == 11 and digits[0] in ("7", "8"):
            phone = "+7" + digits[1:]
            if len(set(phone)) > 3:
                out.append(phone)
    return list(dict.fromkeys(out))


def _clean_emails(raw: list[str]) -> list[str]:
    bad_ext = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")
    out: list[str] = []
    for e in raw:
        low = e.lower()
        if any(low.endswith(x) for x in bad_ext):
            continue
        if "example.com" in low or "domain.com" in low:
            continue
        out.append(e)
    return list(dict.fromkeys(out))


def _extract_ig_usernames(html: str) -> list[str]:
    skip = {"p", "reel", "reels", "stories", "explore", "accounts", "about", "developer", "legal", ""}
    return [f"@{m}" for m in INSTAGRAM_RE.findall(html) if m.lower() not in skip]


def _find_director(text: str) -> Optional[str]:
    for pat in _DIRECTOR_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return None


def _find_activity(text: str) -> Optional[str]:
    for pat in _ACTIVITY_PATTERNS:
        m = pat.search(text)
        if m:
            val = m.group(1).strip()
            if len(val) > 5:
                return val[:200]
    return None


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class PageData:
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    instagrams: list[str] = field(default_factory=list)
    director: Optional[str] = None
    activity: Optional[str] = None


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_company_website(url: str) -> PageData:
    data = PageData()
    base = url.rstrip("/")

    for suffix in ("", "/contacts", "/contact", "/kontakty"):
        html = _fetch(base + suffix)
        if not html:
            continue
        data.phones.extend(clean_phones(RAW_PHONE_RE.findall(html)))
        data.emails.extend(_clean_emails(EMAIL_RE.findall(html)))
        data.instagrams.extend(_extract_ig_usernames(html))

    data.phones = list(dict.fromkeys(data.phones))
    data.emails = list(dict.fromkeys(data.emails))
    data.instagrams = list(dict.fromkeys(data.instagrams))
    return data


def parse_catalog_page(url: str) -> PageData:
    data = PageData()
    html = _fetch(url)
    if not html:
        return data

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    data.director = _find_director(text)
    data.activity = _find_activity(text)
    data.phones = clean_phones(RAW_PHONE_RE.findall(text))
    data.emails = _clean_emails(EMAIL_RE.findall(text))
    return data


def extract_from_snippets(results: list[dict]) -> PageData:
    data = PageData()
    for r in results:
        snippet = r.get("snippet", "")
        data.phones.extend(clean_phones(RAW_PHONE_RE.findall(snippet)))
        data.emails.extend(_clean_emails(EMAIL_RE.findall(snippet)))
    data.phones = list(dict.fromkeys(data.phones))
    data.emails = list(dict.fromkeys(data.emails))
    return data
