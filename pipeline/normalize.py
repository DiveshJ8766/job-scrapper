"""Text cleanup, URL canonicalization and the keys used for deduplication."""

from __future__ import annotations

import hashlib
import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .cities import find_cities, mentions_remote

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_RE = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr|section)[^>]*>", re.IGNORECASE)
_WS_RE = re.compile(r"[ \t\f\v]+")
_NL_RE = re.compile(r"\n\s*\n+")


def html_to_text(raw: str | None) -> str | None:
    """Convert (possibly entity-escaped) HTML into readable plain text."""
    if not raw:
        return None
    text = html.unescape(raw)          # Greenhouse returns escaped HTML
    if "<" in text:
        text = _BLOCK_RE.sub("\n", text)
        text = _TAG_RE.sub(" ", text)
        text = html.unescape(text)
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = _NL_RE.sub("\n\n", text).strip()
    return text or None


# Query parameters that only track the visitor and never identify the job.
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "gh_src", "lever-source", "lever-origin", "source", "src", "ref", "referrer",
    "trk", "fbclid", "gclid", "mc_cid", "mc_eid", "se", "v", "via",
}
# Hosts whose query string never identifies the job (the ad id lives in the path).
_PATH_ONLY_HOSTS = ("adzuna.",)


def canonicalize_url(url: str) -> str:
    """Stable form of a job URL: lowercase host, no www, no tracking params, no fragment."""
    parts = urlsplit(url.strip())
    scheme = "https" if parts.scheme in ("http", "https", "") else parts.scheme
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+", "/", parts.path or "/")
    if len(path) > 1:
        path = path.rstrip("/")
    if any(h in host for h in _PATH_ONLY_HOSTS):
        query = ""
    else:
        kept = [
            (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
            if k.lower() not in _TRACKING_PARAMS and not k.lower().startswith("utm_")
        ]
        query = urlencode(sorted(kept))
    return urlunsplit((scheme, host, path, query, ""))


_COMPANY_SUFFIXES = [
    "private limited", "pvt ltd", "pvt. ltd", "pvt", "limited", "ltd", "inc", "llc",
    "llp", "corp", "corporation", "co", "plc", "gmbh", "india",
]
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_company(name: str) -> str:
    s = _NON_ALNUM.sub(" ", name.lower().replace("&", " and ")).strip()
    changed = True
    while changed and s:
        changed = False
        for suffix in _COMPANY_SUFFIXES:
            token = " " + suffix.replace(".", "")
            if s.endswith(token):
                s = s[: -len(token)].strip()
                changed = True
    return re.sub(r"\s+", " ", s)


_TITLE_ABBREV = {
    "sr": "senior", "jr": "junior", "engg": "engineer", "eng": "engineer",
    "mgr": "manager", "dev": "developer", "swe": "software engineer",
}


def normalize_title(title: str) -> str:
    s = _NON_ALNUM.sub(" ", title.lower().replace("&", " and ")).strip()
    words = [_TITLE_ABBREV.get(w, w) for w in s.split()]
    return " ".join(words)


def location_key(location_raw: str | None) -> str:
    """Location component of the dedupe key: sorted canonical cities, else cleaned text."""
    cities = sorted(find_cities(location_raw))
    if mentions_remote(location_raw):
        cities.append("remote")
    if cities:
        return ",".join(c.lower() for c in cities)
    return _NON_ALNUM.sub(" ", (location_raw or "").lower()).strip()


def dedupe_key(company: str, title: str, location_raw: str | None) -> str:
    return f"{normalize_company(company)}|{normalize_title(title)}|{location_key(location_raw)}"


def content_hash(
    title: str,
    company: str,
    location_raw: str | None,
    employment_type_raw: str | None,
    description: str | None,
) -> str:
    """Hash of every field the classifier looks at. Changes trigger reclassification."""
    parts = [title, company, location_raw or "", employment_type_raw or "", description or ""]
    joined = "\x1f".join(re.sub(r"\s+", " ", p).strip() for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
