"""Settings loaded from environment variables (and a local .env file if present).

The same .env file at the repository root is read by both Next.js and this
Python pipeline. In GitHub Actions the values come from repository secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env", override=False)


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    return float(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    database_url: str
    adzuna_app_id: str | None
    adzuna_app_key: str | None
    llm_provider: str
    llm_model: str
    gemini_api_key: str | None
    openai_api_key: str | None
    llm_max_rpm: int
    llm_max_jobs_per_run: int
    llm_temperature: float
    http_timeout: float
    user_agent: str


def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
    provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    default_model = "gemini-2.5-flash-lite" if provider == "gemini" else "gpt-4o-mini"
    return Settings(
        database_url=database_url,
        adzuna_app_id=os.getenv("ADZUNA_APP_ID") or None,
        adzuna_app_key=os.getenv("ADZUNA_APP_KEY") or None,
        llm_provider=provider,
        llm_model=os.getenv("LLM_MODEL", "").strip() or default_model,
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        llm_max_rpm=_int("LLM_MAX_RPM", 12),
        llm_max_jobs_per_run=_int("LLM_MAX_JOBS_PER_RUN", 900),
        llm_temperature=_float("LLM_TEMPERATURE", 0.0),
        http_timeout=_float("HTTP_TIMEOUT_SECONDS", 30.0),
        user_agent=os.getenv(
            "HTTP_USER_AGENT",
            "FresherJobsAI/1.0 (+https://github.com/DiveshJ8766/job-scrapper)",
        ),
    )
