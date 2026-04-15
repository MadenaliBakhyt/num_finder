"""Phone-number extractor. Fetches a company website and scrapes phones."""
from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru,en;q=0.9,kk;q=0.8",
}

REQUEST_TIMEOUT = 10  # seconds
MAX_PAGES = 6

# Broad phone regex: matches +7/8 country codes with common separators.
PHONE_RE = re.compile(
    r"(?:\+7|\b8)\s?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"
)

# Candidate contact paths to probe in addition to the home page.
CONTACT_PATHS = (
    "",
    "/contacts",
    "/contact",
    "/kontakty",
    "/kontakti",
    "/ru/contacts",
    "/ru/kontakty",
    "/about/contacts",
    "/about",
)


def _normalize_base(url: str) -> Optional[str]:
    """Return a scheme+host base URL, or None if the URL is unusable."""
    if not url:
        return None
    if not urlparse(url).scheme:
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _fetch(url: str) -> Optional[str]:
    try:
        resp = requests.get(
            url, timeout=REQUEST_TIMEOUT, headers=HEADERS, allow_redirects=True
        )
        if resp.status_code != 200:
            return None
        ctype = resp.headers.get("Content-Type", "")
        if "html" not in ctype and "text" not in ctype:
            return None
        return resp.text
    except requests.RequestException as e:
        logger.debug("fetch failed %s: %s", url, e)
        return None
    except Exception as e:
        logger.debug("unexpected fetch error %s: %s", url, e)
        return None


def _extract_phones(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")

    # Prefer tel: links — they're the most reliable signal.
    tel_hits: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().startswith("tel:"):
            tel_hits.append(href[4:])

    text = soup.get_text(" ", strip=True)
    text_hits = PHONE_RE.findall(text)
    tel_text_hits = PHONE_RE.findall(" ".join(tel_hits))

    # De-duplicate while preserving order.
    seen = set()
    ordered: list[str] = []
    for hit in tel_text_hits + text_hits:
        norm = re.sub(r"\s+", " ", hit).strip()
        if norm and norm not in seen:
            seen.add(norm)
            ordered.append(norm)
    return ordered


def _discover_contact_links(html: str, base: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = (a.get_text() or "").lower()
        lowered = href.lower()
        if (
            "contact" in lowered
            or "контакт" in lowered
            or "kontakt" in lowered
            or "contact" in text
            or "контакт" in text
        ):
            links.append(urljoin(base + "/", href))
    return links


def extract_phone_from_website(url: str) -> Optional[str]:
    """Try to find a phone number on the site at ``url``."""
    base = _normalize_base(url)
    if not base:
        logger.info("bad base url: %r", url)
        return None

    visited: set[str] = set()
    queue: list[str] = [base + p for p in CONTACT_PATHS]

    pages_checked = 0
    while queue and pages_checked < MAX_PAGES:
        page = queue.pop(0)
        if page in visited:
            continue
        visited.add(page)
        pages_checked += 1

        logger.info("probe: %s", page)
        html = _fetch(page)
        if not html:
            continue

        phones = _extract_phones(html)
        if phones:
            logger.info("  📞 phones on %s: %s", page, phones)
            return ", ".join(phones[:3])

        # As a fallback, look for explicit contact links and queue them.
        if page == base or page == base + "/":
            for link in _discover_contact_links(html, base):
                if link not in visited and link.startswith(base):
                    queue.append(link)

    return None
