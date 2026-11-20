"""Common shape every source adapter must produce."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class RawJob(BaseModel):
    source_name: str                      # e.g. "greenhouse:postman", "adzuna"
    source_job_id: str                    # stable id within that source
    title: str
    company: str
    application_url: str
    description: str | None = None        # plain text
    location_raw: str | None = None
    employment_type_raw: str | None = None
    posted_at: datetime | None = None
    is_aggregator: bool = False           # True for aggregators such as Adzuna
    extra: dict = Field(default_factory=dict)

    @field_validator("title", "company", "application_url", "source_job_id")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("must not be blank")
        return v
