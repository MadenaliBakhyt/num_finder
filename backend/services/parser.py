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

# Emails from catalog/registry sites — never the company's own
_BAD_EMAIL_DOMAINS = [
    "prg.kz", "cdb.kz", "kompra.kz", "statsnet.co",
    "gov.kz", "ecc.kz", "uchet.kz", "kiberon.kz",
    "adata.kz", "enbek.kz", "qoldau.kz",
    "example.com", "domain.com",
]

_JUNK_EMAILS = {"rating@mail.ru"}

# Registry/support phone numbers (appear on 10+ unrelated companies)
_JUNK_PHONES = {
    "+77172609090", "+77172735515", "+77059565388",  # goszakup.gov.kz
    "+77780030198",  # kiberon.kz
}

_IG_SKIP = {
    "p", "reel", "reels", "stories", "explore", "accounts",
    "about", "developer", "legal", "static", "api", "",
}

# Instagram accounts that belong to catalog/registry sites, not companies
_IG_CATALOG_ACCOUNTS = {
    "uchet24", "uchet.kz", "enbek.kz", "adata.kz", "cdb.kz",
    "kiberon.kz", "kompra.kz", "prg.kz",
}

# Activity must NOT contain these — they indicate sidebar/menu garbage
_ACTIVITY_GARBAGE = re.compile(
    r"Связи|Суды|Риски|Получите расширенный|Редактировать|Скрыть|"
    r"Распечатать|Подписаться|Сводная инфор|Сотрудники \d",
    re.I,
)


@dataclass
class PageData:
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    instagrams: list[str] = field(default_factory=list)
    director: Optional[str] = None
    activity: Optional[str] = None
    website: Optional[str] = None


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
            if len(set(phone)) > 3 and phone not in _JUNK_PHONES:
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
        if low in _JUNK_EMAILS:
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
        if "." in username:
            continue
        if username in _IG_CATALOG_ACCOUNTS:
            continue
        result.append(f"@{m}")
    return list(dict.fromkeys(result))


def _validate_director(text: str | None) -> Optional[str]:
    """Director must be 2-3 Cyrillic/Latin words, each capitalized."""
    if not text:
        return None
    text = text.strip()
    # Remove trailing noise like "Проверено:", links, etc.
    text = re.sub(r"\s*(Проверено|Национальное|Комитет).*", "", text).strip()
    words = text.split()
    if len(words) < 2 or len(words) > 4:
        return None
    # Each word should start with uppercase
    for w in words:
        if not re.match(r"^[А-ЯЁA-Z]", w):
            return None
    return text


def _validate_activity(text: str | None) -> Optional[str]:
    """Activity must be a real business description, not sidebar garbage."""
    if not text:
        return None
    text = text.strip()
    # Clean trailing metadata FIRST, then check for garbage
    text = re.sub(r"\s*БИН[:\s].*", "", text).strip()
    text = re.sub(r"\s*Проверено[:\s].*", "", text).strip()
    text = re.sub(r"\s*Различается.*", "", text).strip()
    text = re.sub(r"\s*Редактировать.*", "", text).strip()
    text = re.sub(r"\s*Распечатать.*", "", text).strip()
    text = re.sub(r"\s*New\b.*", "", text).strip()
    if _ACTIVITY_GARBAGE.search(text):
        return None
    if len(text) < 10:
        return None
    return text[:200]


# ---------------------------------------------------------------------------
# Company website parser
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
        data.instagrams.extend(_extract_ig(html))

    data.phones = list(dict.fromkeys(data.phones))
    data.emails = list(dict.fromkeys(data.emails))
    data.instagrams = list(dict.fromkeys(data.instagrams))
    return data


# ---------------------------------------------------------------------------
# ba.prg.kz parser
# ---------------------------------------------------------------------------

def parse_baprg_page(url: str) -> PageData:
    data = PageData()
    html = _fetch(url)
    if not html:
        return data

    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text("\n", strip=True)

    # ── Director ────────────────────────────────────────────────────
    # ba.prg.kz shows: "Руководитель компании\n<NAME>"
    # The name is typically in ALL CAPS Cyrillic
    for pattern in [
        r"Руководитель\s+компании\s*\n?\s*([А-ЯЁ][А-ЯЁа-яё\s\-]{5,60})",
        r"Первый руководитель\s*\n?\s*([А-ЯЁ][А-ЯЁа-яё\s\-]{5,60})",
        r"Руководитель\s*[:\n]\s*([А-ЯЁ][А-ЯЁа-яё\s\-]{5,60})",
    ]:
        m = re.search(pattern, full_text)
        if m:
            candidate = m.group(1).strip()
            # Take first 2-4 words (the name)
            words = candidate.split()
            name_words = []
            for w in words:
                if re.match(r"^[А-ЯЁа-яё\-]+$", w):
                    name_words.append(w)
                else:
                    break
                if len(name_words) >= 4:
                    break
            if len(name_words) >= 2:
                data.director = _validate_director(" ".join(name_words))
                if data.director:
                    break

    # ── Activity (Основной ОКЭД) ───────────────────────────────────
    # Format: "Основной ОКЭД\n46909 Оптовая торговля..." or similar
    for pattern in [
        r"Основной\s+ОКЭД\s*\n?\s*(\d{4,5}\s+[^\n]{10,})",
        r"Основной\s+ОКЭД\s*\n?\s*([^\n]{10,200})",
        r"Вид\s+деятельности\s*[:\n]\s*([^\n]{10,200})",
    ]:
        m = re.search(pattern, full_text)
        if m:
            candidate = m.group(1).strip()
            validated = _validate_activity(candidate)
            if validated:
                data.activity = validated
                break

    # ── Phone (from tel: links in Контактные данные section) ───────
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.lower().startswith("tel:"):
            phone_text = href[4:].strip()
            data.phones.extend(clean_phones([phone_text]))

    # Fallback: regex near "Телефон" label
    if not data.phones:
        m = re.search(r"Телефон\s*\n?\s*(\+?\d[\d\s\-\(\)]{8,})", full_text)
        if m:
            data.phones = clean_phones([m.group(1)])

    # ── Email (from mailto: links) ─────────────────────────────────
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.lower().startswith("mailto:"):
            email = href[7:].split("?")[0].strip()
            data.emails.append(email)

    if not data.emails:
        m = re.search(r"E-mail\s*\n?\s*(\S+@\S+)", full_text)
        if m:
            data.emails.append(m.group(1))

    data.emails = _clean_emails(data.emails)

    # ── Website from ba.prg.kz contacts ────────────────────────────
    m = re.search(r"Веб-сайт\s*\n?\s*(https?://\S+|www\.\S+)", full_text)
    if m:
        found = m.group(1).strip()
        if "отсутствует" not in found.lower():
            if not found.startswith("http"):
                found = "https://" + found
            data.website = found

    data.phones = list(dict.fromkeys(data.phones))
    return data
