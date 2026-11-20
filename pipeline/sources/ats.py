"""Adapters for public applicant-tracking-system job board APIs (no auth needed).

Each board is fetched as one unit, so one broken board never affects another.
Only postings located in India (or remote within India) are kept.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ..cities import find_cities
from ..models import RawJob
from ..normalize import html_to_text
from .http import PoliteClient, SourceError

_INDIA_RE = re.compile(r"\b(india|bharat)\b", re.IGNORECASE)


def is_india_location(*texts: str | None, country: str | None = None) -> bool:
    if country and country.strip().upper() in {"IN", "IND", "INDIA"}:
        return True
    return any(t and (_INDIA_RE.search(t) or find_cities(t)) for t in texts)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _join_location(location: str | None, offices: str | None) -> str | None:
    """Combine a posting's location label with its office list when they add information."""
    if not offices or not offices.strip(", "):
        return location
    if not location:
        return offices
    if offices.lower() in location.lower():
        return location
    return f"{location} ({offices})"


# --------------------------------------------------------------------- Greenhouse
def fetch_greenhouse(client: PoliteClient, token: str, company: str) -> list[RawJob]:
    data = client.get_json(
        f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", params={"content": "true"}
    )
    if not isinstance(data, dict) or "jobs" not in data:
        raise SourceError(f"greenhouse:{token}: unexpected response shape")
    jobs: list[RawJob] = []
    for j in data["jobs"]:
        location = (j.get("location") or {}).get("name")
        offices = ", ".join(o.get("location") or o.get("name") or "" for o in j.get("offices") or [])
        if not is_india_location(location, offices):
            continue
        meta_type = None
        for m in j.get("metadata") or []:
            if isinstance(m, dict) and "employment" in str(m.get("name", "")).lower():
                meta_type = str(m.get("value") or "") or None
        jobs.append(RawJob(
            source_name=f"greenhouse:{token}",
            source_job_id=str(j["id"]),
            title=j.get("title", ""),
            company=j.get("company_name") or company,
            application_url=j.get("absolute_url", ""),
            description=html_to_text(j.get("content")),
            location_raw=_join_location(location, offices),
            employment_type_raw=meta_type,
            posted_at=_parse_iso(j.get("first_published") or j.get("updated_at")),
        ))
    return jobs


# --------------------------------------------------------------------- Lever
def fetch_lever(client: PoliteClient, token: str, company: str) -> list[RawJob]:
    data = client.get_json(f"https://api.lever.co/v0/postings/{token}", params={"mode": "json"})
    if not isinstance(data, list):
        raise SourceError(f"lever:{token}: unexpected response shape")
    jobs: list[RawJob] = []
    for p in data:
        cats = p.get("categories") or {}
        all_locs = cats.get("allLocations") or []
        location = ", ".join(all_locs) if all_locs else cats.get("location")
        if not is_india_location(location, country=p.get("country")):
            continue
        if p.get("workplaceType") == "remote" and location and "remote" not in location.lower():
            location = f"{location} (Remote)"
        sections = [p.get("descriptionPlain") or ""]
        for lst in p.get("lists") or []:
            sections.append(f"{lst.get('text', '')}\n{html_to_text(lst.get('content')) or ''}")
        sections.append(p.get("additionalPlain") or "")
        created = p.get("createdAt")
        jobs.append(RawJob(
            source_name=f"lever:{token}",
            source_job_id=str(p["id"]),
            title=p.get("text", ""),
            company=company,
            application_url=p.get("hostedUrl") or p.get("applyUrl") or "",
            description="\n\n".join(s.strip() for s in sections if s and s.strip()) or None,
            location_raw=location,
            employment_type_raw=cats.get("commitment"),
            posted_at=datetime.fromtimestamp(created / 1000, tz=timezone.utc) if created else None,
        ))
    return jobs


# --------------------------------------------------------------------- Ashby
def fetch_ashby(client: PoliteClient, token: str, company: str) -> list[RawJob]:
    data = client.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    if not isinstance(data, dict) or "jobs" not in data:
        raise SourceError(f"ashby:{token}: unexpected response shape")
    jobs: list[RawJob] = []
    for j in data["jobs"]:
        if j.get("isListed") is False:
            continue
        locs = [j.get("location") or ""] + [
            s.get("location") or "" for s in j.get("secondaryLocations") or []
        ]
        location = ", ".join(dict.fromkeys(x for x in locs if x))
        country = ((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry")
        if not is_india_location(location, country=country):
            continue
        if j.get("isRemote") and "remote" not in location.lower():
            location = f"{location} (Remote)"
        jobs.append(RawJob(
            source_name=f"ashby:{token}",
            source_job_id=str(j["id"]),
            title=j.get("title", ""),
            company=company,
            application_url=j.get("jobUrl") or j.get("applyUrl") or "",
            description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
            location_raw=location or None,
            employment_type_raw=j.get("employmentType"),
            posted_at=_parse_iso(j.get("publishedAt")),
        ))
    return jobs


ATS_FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}
