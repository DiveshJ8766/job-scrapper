"""Classify new/changed jobs with the LLM, validate, post-process, log tokens and cost."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import psycopg
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ..cities import canonical_city, city_supported_by, mentions_remote
from ..config import Settings
from .llm import LLMClient, PermanentLLMError, TransientLLMError
from .pricing import estimate_cost
from .prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from .schema import LLMClassification

log = logging.getLogger(__name__)

MAX_ATTEMPTS_PER_RUN = 3        # API retries + one repair attempt for invalid output
MAX_TOTAL_FAILURES = 3          # after this many failed runs a job is left as 'failed'


class InvalidOutput(ValueError):
    pass


@dataclass
class FinalClassification:
    role: str
    city: str
    cities: list[str]
    is_remote: bool
    job_type: str
    experience_level: str
    confidence: str
    dropped_cities: list[str] = field(default_factory=list)

    def as_json(self) -> dict:
        return self.__dict__.copy()


def parse_output(text: str) -> LLMClassification:
    """Parse and schema-validate raw model text. Tolerates ```json fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned[4:] if cleaned.lower().startswith("json") else cleaned
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise InvalidOutput(f"not valid JSON: {exc}") from exc
    try:
        return LLMClassification.model_validate(data)
    except ValidationError as exc:
        raise InvalidOutput(f"schema validation failed: {exc.errors(include_url=False)}") from exc


def postprocess(out: LLMClassification, *, title: str, location_raw: str | None,
                description: str | None) -> FinalClassification:
    """Normalize city names and drop any city the posting does not actually mention."""
    cities: list[str] = []
    dropped: list[str] = []
    for c in out.cities:
        name = c.strip()
        if not name or name.lower() in {"remote", "india", "unknown", "anywhere"}:
            continue
        canonical = canonical_city(name) or name.title()
        if not city_supported_by(name, location_raw, title, description) and \
                not city_supported_by(canonical, location_raw, title, description):
            dropped.append(name)          # hallucination guard
            continue
        if canonical not in cities:
            cities.append(canonical)
    is_remote = bool(out.is_remote and mentions_remote(" ".join(
        t for t in (location_raw, title, description) if t)))
    if out.is_remote and not is_remote:
        dropped.append("Remote")
    display = list(cities)
    if is_remote:
        display.append("Remote")
    if not display:
        display = ["Unknown"]
    return FinalClassification(
        role=out.role, city=display[0], cities=display, is_remote=is_remote,
        job_type=out.job_type, experience_level=out.experience_level,
        confidence=out.confidence, dropped_cities=dropped,
    )


def _log(conn, *, job_id, run_id, model, status, attempt, tin, tout, latency, result, error):
    conn.execute(
        """INSERT INTO classification_logs (job_id, pipeline_run_id, model_name, prompt_version,
               status, attempt, input_tokens, output_tokens, estimated_cost, latency_ms,
               classification_result, error)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (job_id, run_id, model, PROMPT_VERSION, status, attempt, tin, tout,
         estimate_cost(model, tin, tout), latency, Jsonb(result) if result else None, error),
    )


def select_jobs_to_classify(conn: psycopg.Connection, limit: int) -> list[dict]:
    return conn.execute(
        """SELECT id, title, company, location_raw, employment_type_raw, description, content_hash
             FROM jobs
            WHERE is_active AND (
                  classification_status = 'pending'
               OR (classification_status = 'failed' AND classification_attempts < %s)
               OR (classification_status = 'classified' AND prompt_version IS DISTINCT FROM %s))
            ORDER BY first_seen_at DESC, id
            LIMIT %s""",
        (MAX_TOTAL_FAILURES, PROMPT_VERSION, limit),
    ).fetchall()


def classify_job(conn: psycopg.Connection, llm: LLMClient, job: dict,
                 run_id: int | None) -> FinalClassification | None:
    user = build_user_prompt(job["title"], job["company"], job["location_raw"],
                             job["employment_type_raw"], job["description"])
    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS_PER_RUN + 1):
        prompt = user if attempt == 1 or not last_error.startswith("invalid") else (
            user + "\n\nYour previous answer was rejected: " + last_error[:300]
            + "\nReturn a corrected JSON object that matches the schema exactly.")
        try:
            resp = llm.complete_json(SYSTEM_PROMPT, prompt)
        except TransientLLMError as exc:
            last_error = f"api: {exc}"
            _log(conn, job_id=job["id"], run_id=run_id, model=llm.model, status="api_error",
                 attempt=attempt, tin=0, tout=0, latency=None, result=None, error=str(exc)[:1000])
            time.sleep(min(2 ** attempt * 2, 30))
            continue
        except PermanentLLMError as exc:
            _log(conn, job_id=job["id"], run_id=run_id, model=llm.model, status="api_error",
                 attempt=attempt, tin=0, tout=0, latency=None, result=None, error=str(exc)[:1000])
            raise
        try:
            parsed = parse_output(resp.text)
        except InvalidOutput as exc:
            last_error = f"invalid output: {exc}"
            _log(conn, job_id=job["id"], run_id=run_id, model=llm.model, status="invalid_output",
                 attempt=attempt, tin=resp.input_tokens, tout=resp.output_tokens,
                 latency=resp.latency_ms, result={"raw_text": resp.text[:2000]}, error=str(exc)[:1000])
            continue
        final = postprocess(parsed, title=job["title"], location_raw=job["location_raw"],
                            description=job["description"])
        _log(conn, job_id=job["id"], run_id=run_id, model=llm.model, status="success",
             attempt=attempt, tin=resp.input_tokens, tout=resp.output_tokens,
             latency=resp.latency_ms, result={"llm": parsed.model_dump(), "final": final.as_json()},
             error=None)
        conn.execute(
            """UPDATE jobs SET role=%s, city=%s, cities=%s, is_remote=%s, job_type=%s,
                   experience_level=%s, classification_status='classified',
                   classified_hash=%s, classification_model=%s, prompt_version=%s,
                   classified_at=now(), updated_at=now()
               WHERE id=%s""",
            (final.role, final.city, final.cities, final.is_remote, final.job_type,
             final.experience_level, job["content_hash"], llm.model, PROMPT_VERSION, job["id"]),
        )
        return final
    log.warning("job %s: classification failed: %s", job["id"], last_error)
    conn.execute(
        """UPDATE jobs SET classification_status='failed',
               classification_attempts = classification_attempts + 1, updated_at=now()
           WHERE id=%s""",
        (job["id"],),
    )
    return None


def classify_pending(conn: psycopg.Connection, settings: Settings, run_id: int | None,
                     limit: int | None = None) -> tuple[int, int]:
    """Returns (classified, failed). Commits after every job so progress survives crashes."""
    key = settings.gemini_api_key if settings.llm_provider == "gemini" else settings.openai_api_key
    llm = LLMClient(settings.llm_provider, settings.llm_model, key or "",
                    temperature=settings.llm_temperature)
    jobs = select_jobs_to_classify(conn, limit or settings.llm_max_jobs_per_run)
    log.info("classifying %d jobs with %s/%s", len(jobs), settings.llm_provider, settings.llm_model)
    interval = 60.0 / max(settings.llm_max_rpm, 1)
    ok = failed = consecutive_permanent = 0
    last_call = 0.0
    for job in jobs:
        wait = interval - (time.monotonic() - last_call)
        if wait > 0:
            time.sleep(wait)
        last_call = time.monotonic()
        try:
            result = classify_job(conn, llm, job, run_id)
            consecutive_permanent = 0
        except PermanentLLMError as exc:
            # One bad posting (e.g. blocked content) must not stop the run, but repeated
            # permanent errors almost always mean a bad key or model name: stop early.
            conn.execute(
                """UPDATE jobs SET classification_status='failed',
                       classification_attempts = classification_attempts + 1 WHERE id=%s""",
                (job["id"],))
            conn.commit()
            consecutive_permanent += 1
            failed += 1
            if consecutive_permanent >= 3:
                raise PermanentLLMError(f"stopping classification: {exc}") from exc
            continue
        conn.commit()
        ok, failed = (ok + 1, failed) if result else (ok, failed + 1)
    return ok, failed
