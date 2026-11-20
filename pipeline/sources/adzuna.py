"""Adzuna Jobs API (India). Requires ADZUNA_APP_ID / ADZUNA_APP_KEY.

Terms: every displayed Adzuna listing must carry a visible "Jobs by Adzuna"
attribution (the frontend renders it on every card sourced from Adzuna).
Descriptions are snippets (~500 chars), and links go through an Adzuna redirect.
"""

from __future__ import annotations

from datetime import datetime

from ..models import RawJob
from ..normalize import html_to_text
from .http import PoliteClient, SourceError

API = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def _employment_type(r: dict) -> str | None:
    parts = [r.get("contract_time"), r.get("contract_type")]
    joined = ", ".join(p.replace("_", " ") for p in parts if p)
    return joined or None


def fetch_adzuna_query(client: PoliteClient, app_id: str, app_key: str, *, country: str,
                       query: str, pages: int, per_page: int, max_days_old: int,
                       delay: float) -> list[RawJob]:
    jobs: list[RawJob] = []
    for page in range(1, pages + 1):
        data = client.get_json(
            API.format(country=country, page=page),
            params={
                "app_id": app_id, "app_key": app_key, "what": query,
                "results_per_page": per_page, "max_days_old": max_days_old,
                "sort_by": "date", "content-type": "application/json",
            },
            min_interval=delay,
        )
        if not isinstance(data, dict) or "results" not in data:
            raise SourceError(f"adzuna '{query}' page {page}: unexpected response shape")
        results = data["results"]
        for r in results:
            company = ((r.get("company") or {}).get("display_name") or "").strip()
            title = html_to_text(r.get("title")) or ""
            if not company or not title or not r.get("redirect_url"):
                continue  # incomplete listing; nothing reliable to show
            created = r.get("created")
            jobs.append(RawJob(
                source_name="adzuna",
                source_job_id=str(r["id"]),
                title=title,
                company=company,
                application_url=r["redirect_url"],
                description=html_to_text(r.get("description")),
                location_raw=(r.get("location") or {}).get("display_name"),
                employment_type_raw=_employment_type(r),
                posted_at=datetime.fromisoformat(created.replace("Z", "+00:00")) if created else None,
                is_aggregator=True,
                extra={"category": (r.get("category") or {}).get("label")},
            ))
        if len(results) < per_page:
            break
    return jobs
