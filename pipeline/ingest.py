"""Idempotent upsert with deduplication.

Match order for an incoming record:
  1. Same source + same source_job_id seen before          -> same job (refresh it)
  2. Same canonical application URL                         -> same job (duplicate)
  3. Same dedupe_key (normalized company|title|location) AND
     the records come from different sources (or one is an
     aggregator), AND the location part is known            -> same job (duplicate)
  otherwise                                                 -> new job

Rule 3 is deliberately conservative: two postings with the same title on the
same company's own board are different openings (different source ids), so
they are never merged with each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import psycopg

from .models import RawJob
from .normalize import canonicalize_url, content_hash, dedupe_key

AGGREGATOR_SOURCES = {"adzuna"}


class Outcome(str, Enum):
    INSERTED = "inserted"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    MERGED = "merged_duplicate"


def _priority(source_name: str) -> int:
    """Direct employer boards beat aggregators as the displayed record."""
    return 1 if source_name in AGGREGATOR_SOURCES else 2


@dataclass
class Prepared:
    raw: RawJob
    canonical_url: str
    dedupe_key: str
    content_hash: str


def prepare(raw: RawJob) -> Prepared:
    return Prepared(
        raw=raw,
        canonical_url=canonicalize_url(raw.application_url),
        dedupe_key=dedupe_key(raw.company, raw.title, raw.location_raw),
        content_hash=content_hash(raw.title, raw.company, raw.location_raw,
                                  raw.employment_type_raw, raw.description),
    )


_CONTENT_UPDATE = """
UPDATE jobs SET
  title=%(title)s, company=%(company)s, description=%(description)s,
  location_raw=%(location_raw)s, employment_type_raw=%(employment_type_raw)s,
  application_url=%(application_url)s, canonical_url=%(canonical_url)s,
  source_name=%(source_name)s, source_job_id=%(source_job_id)s,
  dedupe_key=%(dedupe_key)s, posted_at=COALESCE(%(posted_at)s, posted_at),
  content_hash=%(content_hash)s,
  classification_status = CASE WHEN classified_hash = %(content_hash)s
                               THEN classification_status ELSE 'pending' END,
  last_seen_at=now(), is_active=TRUE, updated_at=now()
WHERE id=%(id)s
"""


def _params(p: Prepared, job_id: int | None = None) -> dict:
    r = p.raw
    return {
        "id": job_id, "title": r.title, "company": r.company, "description": r.description,
        "location_raw": r.location_raw, "employment_type_raw": r.employment_type_raw,
        "application_url": r.application_url, "canonical_url": p.canonical_url,
        "source_name": r.source_name, "source_job_id": r.source_job_id,
        "dedupe_key": p.dedupe_key, "posted_at": r.posted_at, "content_hash": p.content_hash,
    }


def _link_source(conn: psycopg.Connection, job_id: int, r: RawJob) -> None:
    conn.execute(
        """INSERT INTO job_sources (job_id, source_name, source_job_id, source_url)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (source_name, source_job_id)
           DO UPDATE SET last_seen_at = now(), source_url = EXCLUDED.source_url,
                         job_id = EXCLUDED.job_id""",
        (job_id, r.source_name, r.source_job_id, r.application_url),
    )


def upsert(conn: psycopg.Connection, p: Prepared) -> Outcome:
    r = p.raw

    # 1. Known source record
    known = conn.execute(
        """SELECT j.id, j.source_name, j.source_job_id, j.content_hash
             FROM job_sources s JOIN jobs j ON j.id = s.job_id
            WHERE s.source_name=%s AND s.source_job_id=%s""",
        (r.source_name, r.source_job_id),
    ).fetchone()
    if known:
        _link_source(conn, known["id"], r)
        is_displayed = (known["source_name"], known["source_job_id"]) == (r.source_name, r.source_job_id)
        if is_displayed and known["content_hash"] != p.content_hash:
            clash = conn.execute(
                "SELECT id FROM jobs WHERE canonical_url=%s AND id<>%s", (p.canonical_url, known["id"])
            ).fetchone()
            if clash is None:
                conn.execute(_CONTENT_UPDATE, _params(p, known["id"]))
                return Outcome.UPDATED
        conn.execute(
            "UPDATE jobs SET last_seen_at=now(), is_active=TRUE WHERE id=%s", (known["id"],)
        )
        return Outcome.UNCHANGED

    # 2. Same canonical URL
    match = conn.execute(
        "SELECT id, source_name FROM jobs WHERE canonical_url=%s", (p.canonical_url,)
    ).fetchone()

    # 3. Conservative secondary match on normalized company|title|location
    if match is None and not p.dedupe_key.endswith("|"):
        candidates = conn.execute(
            "SELECT id, source_name FROM jobs WHERE dedupe_key=%s ORDER BY id", (p.dedupe_key,)
        ).fetchall()
        for c in candidates:
            if (c["source_name"] != r.source_name or r.source_name in AGGREGATOR_SOURCES):
                match = c
                break

    if match is not None:
        _link_source(conn, match["id"], r)
        if _priority(r.source_name) > _priority(match["source_name"]):
            # A direct employer posting replaces an aggregator copy as the displayed record.
            conn.execute(_CONTENT_UPDATE, _params(p, match["id"]))
        else:
            conn.execute(
                "UPDATE jobs SET last_seen_at=now(), is_active=TRUE WHERE id=%s", (match["id"],)
            )
        return Outcome.MERGED

    # New job
    row = conn.execute(
        """INSERT INTO jobs (title, company, description, location_raw, employment_type_raw,
                             application_url, canonical_url, source_name, source_job_id,
                             dedupe_key, posted_at, content_hash)
           VALUES (%(title)s, %(company)s, %(description)s, %(location_raw)s,
                   %(employment_type_raw)s, %(application_url)s, %(canonical_url)s,
                   %(source_name)s, %(source_job_id)s, %(dedupe_key)s, %(posted_at)s,
                   %(content_hash)s)
           RETURNING id""",
        _params(p),
    ).fetchone()
    _link_source(conn, row["id"], r)
    return Outcome.INSERTED


def deactivate_stale(conn: psycopg.Connection, failed_sources: list[str], days: int = 3) -> int:
    """Hide jobs not seen for `days`, except those tied to a source that failed this run
    (we cannot tell whether those are gone or merely unreachable)."""
    cur = conn.execute(
        """UPDATE jobs j SET is_active=FALSE, updated_at=now()
            WHERE j.is_active
              AND j.last_seen_at < now() - make_interval(days => %s)
              AND NOT EXISTS (SELECT 1 FROM job_sources s
                               WHERE s.job_id=j.id AND s.source_name = ANY(%s))""",
        (days, failed_sources),
    )
    return cur.rowcount
