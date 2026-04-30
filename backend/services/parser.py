"""Phone-number extractor — lightweight regex scraper for KZ numbers."""
from __future__ import annotations

import logging
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_session = requests.Session()
HEADERS = {"User-Agent": "Mozilla/5.0"}
REQUEST_TIMEOUT = 5

RAW_PHONE_RE = re.compile(r"\+?\d[\d\s\-\(\)]{8,}")
CONTACT_PATHS = ("", "/contacts", "/contact")


def _clean_phones(raw_phones: list[str]) -> list[str]:
    cleaned: list[str] = []
    for p in raw_phones:
        digits = re.sub(r"\D", "", p)
        if len(digits) == 11 and (digits.startswith("7") or digits.startswith("8")):
            phone = "+7" + digits[1:]
            if len(set(phone)) > 3:
                cleaned.append(phone)
    return list(dict.fromkeys(cleaned))  # dedupe, keep order


def extract_phone_from_website(url: str) -> Optional[str]:
    try:
        base = url.rstrip("/")
        for suffix in CONTACT_PATHS:
            page = base + suffix
            try:
                r = _session.get(page, timeout=REQUEST_TIMEOUT, headers=HEADERS)
                if r.status_code != 200:
                    continue
                raw = RAW_PHONE_RE.findall(r.text)
                phones = _clean_phones(raw)
                if phones:
                    logger.info("  phones on %s: %s", page, phones)
                    return ", ".join(phones)
            except Exception:
                continue
    except Exception:
        pass
    return None
