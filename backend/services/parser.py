"""Page scrapers — company website and ba.prg.kz parser."""
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

# Catalog / registry emails we should never return as the company's email
_BAD_EMAIL_DOMAINS = [
    "prg.kz", "cdb.kz", "kompra.kz", "statsnet.co",
    "gov.kz", "example.com", "domain.com",
]

_IG_SKIP = {"p", "reel", "reels", "stories", "explore", "accounts",
            "about", "developer", "legal", "static", "api", ""}


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
    website: Optional[str] = None  # website found on ba.prg.kz


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
        if any(d in low for d in _BAD_EMAIL_DOMAINS):
            continue
        out.append(e)
    return list(dict.fromkeys(out))


def _extract_ig(html: str) -> list[str]:
    matches = INSTAGRAM_RE.findall(html)
    result: list[str] = []
    for m in matches:
        username = m.lower()
        if username in _IG_SKIP:
            continue
        if len(username) < 3:
            continue
        result.append(f"@{m}")
    return list(dict.fromkeys(result))


# ---------------------------------------------------------------------------
# Company website parser
# ---------------------------------------------------------------------------

def parse_company_website(url: str) -> PageData:
    """Parse a company's own website for phones, emails, Instagram links."""
    data = PageData()
    base = url.rstrip("/")

    for suffix in ("", "/contacts", "/contact", "/kontakty"):
        html = _fetch(base + suffix)
        if not html:
            continue
        data.phones.extend(clean_phones(RAW_PHONE_RE.findall(html)))
        data.emails.extend(_clean_emails(EMAIL_RE.findall(html)))
        data.instagrams.extend(_extract_ig(html))

    data.phones = list(dict.fromkeys(data.phones))
    data.emails = list(dict.fromkeys(data.emails))
    data.instagrams = list(dict.fromkeys(data.instagrams))
    return data


# ---------------------------------------------------------------------------
# ba.prg.kz parser
# ---------------------------------------------------------------------------

def _get_value_after_label(soup: BeautifulSoup, label_text: str) -> Optional[str]:
    """Find a label element containing `label_text` and return the next
    sibling element's text (typical ba.prg.kz label→value layout)."""
    for el in soup.find_all(string=re.compile(re.escape(label_text), re.I)):
        parent = el.find_parent()
        if not parent:
            continue
        # Try next sibling element
        nxt = parent.find_next_sibling()
        if nxt:
            text = nxt.get_text(" ", strip=True)
            if text and text.lower() not in ("", "информация в источнике отсутствует"):
                return text
        # Try parent's next sibling (in case label is nested deeper)
        parent_row = parent.find_parent()
        if parent_row:
            nxt = parent_row.find_next_sibling()
            if nxt:
                text = nxt.get_text(" ", strip=True)
                if text and text.lower() not in ("", "информация в источнике отсутствует"):
                    return text
    return None


def parse_baprg_page(url: str) -> PageData:
    """Parse a ba.prg.kz company page for director, activity, contacts."""
    data = PageData()
    html = _fetch(url)
    if not html:
        return data

    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text(" ", strip=True)

    # ── Director ────────────────────────────────────────────────────
    for label in ("Руководитель компании", "Первый руководитель", "Руководитель"):
        val = _get_value_after_label(soup, label)
        if val:
            # Clean: take only the name part (uppercase Cyrillic words)
            name_match = re.match(r"([А-ЯЁ][А-ЯЁа-яё\s\-]+)", val)
            if name_match:
                data.director = name_match.group(1).strip()
            else:
                data.director = val[:100]
            break

    # If regex on structured HTML didn't work, try plain text
    if not data.director:
        m = re.search(
            r"Руководитель\s+компании\s+([А-ЯЁ][А-ЯЁа-яё]+\s+[А-ЯЁ][А-ЯЁа-яё]+(?:\s+[А-ЯЁ][А-ЯЁа-яё]+)?)",
            full_text,
        )
        if m:
            data.director = m.group(1).strip()

    # ── Activity (Основной ОКЭД) ───────────────────────────────────
    val = _get_value_after_label(soup, "Основной ОКЭД")
    if val:
        data.activity = val[:200]
    else:
        m = re.search(r"Основной ОКЭД\s+(.+?)(?:Вторичный|КАТО|$)", full_text)
        if m:
            activity = m.group(1).strip()
            # Remove trailing metadata
            activity = re.sub(r"\s*Проверено:.*", "", activity)
            activity = re.sub(r"\s*Различается.*", "", activity)
            if len(activity) > 5:
                data.activity = activity[:200]

    # ── Phone (from tel: links) ────────────────────────────────────
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.lower().startswith("tel:"):
            phone_raw = href[4:]
            phones = clean_phones([phone_raw])
            data.phones.extend(phones)

    # Fallback: regex in "Контактные данные" section text
    if not data.phones:
        m = re.search(r"Телефон\s+([\+\d\s\-\(\)]+)", full_text)
        if m:
            data.phones = clean_phones([m.group(1)])

    # ── Email (from mailto: links) ─────────────────────────────────
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.lower().startswith("mailto:"):
            email = href[7:].split("?")[0].strip()
            data.emails.append(email)

    if not data.emails:
        m = re.search(r"E-mail\s+(\S+@\S+)", full_text)
        if m:
            data.emails.append(m.group(1))

    data.emails = _clean_emails(data.emails)

    # ── Website ────────────────────────────────────────────────────
    val = _get_value_after_label(soup, "Веб-сайт")
    if val and "отсутствует" not in val.lower():
        # Extract URL from text
        url_match = re.search(r"(https?://\S+|www\.\S+|\S+\.\w{2,3})", val)
        if url_match:
            found = url_match.group(1)
            if not found.startswith("http"):
                found = "https://" + found
            data.website = found

    data.phones = list(dict.fromkeys(data.phones))
    return data


# ---------------------------------------------------------------------------
# Snippet extractor (free — no HTTP)
# ---------------------------------------------------------------------------

def extract_from_snippets(results: list[dict]) -> PageData:
    data = PageData()
    for r in results:
        snippet = r.get("snippet", "")
        data.phones.extend(clean_phones(RAW_PHONE_RE.findall(snippet)))
        data.emails.extend(_clean_emails(EMAIL_RE.findall(snippet)))
    data.phones = list(dict.fromkeys(data.phones))
    data.emails = list(dict.fromkeys(data.emails))
    return data
