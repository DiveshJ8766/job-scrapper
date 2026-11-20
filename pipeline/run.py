"""Pipeline entry point: fetch -> normalize -> dedupe/upsert -> deactivate -> classify.

    python -m pipeline.run                     # full run
    python -m pipeline.run --skip-classify     # ingest only
    python -m pipeline.run --skip-fetch        # classify pending jobs only
    python -m pipeline.run --only greenhouse   # only units whose name starts with this

Every source unit (one Adzuna query, one company board) is isolated: an error is
recorded in pipeline_runs.source_stats/errors and the run continues.
Exit code is 1 only when the whole run failed.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from .classify.classifier import classify_pending
from .classify.llm import PermanentLLMError
from .config import Settings, get_settings
from .db import connect, migrate
from .ingest import Outcome, deactivate_stale, prepare, upsert
from .models import RawJob
from .sources.adzuna import fetch_adzuna_query
from .sources.ats import ATS_FETCHERS
from .sources.http import PoliteClient, SourceError

log = logging.getLogger("pipeline")
SOURCES_FILE = Path(__file__).with_name("sources.json")


@dataclass
class Unit:
    name: str                 # label in stats, e.g. "adzuna:data analyst", "lever:cred"
    source_name: str          # value stored on job_sources, e.g. "adzuna", "lever:cred"
    fetch: Callable[[], list[RawJob]]


def build_units(settings: Settings, client: PoliteClient, only: str | None) -> tuple[list[Unit], dict]:
    cfg = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    units: list[Unit] = []
    skipped: dict[str, dict] = {}

    az = cfg.get("adzuna") or {}
    if az.get("enabled"):
        if settings.adzuna_app_id and settings.adzuna_app_key:
            for q in az["queries"]:
                units.append(Unit(
                    f"adzuna:{q}", "adzuna",
                    lambda q=q: fetch_adzuna_query(
                        client, settings.adzuna_app_id, settings.adzuna_app_key,
                        country=az["country"], query=q, pages=az["pages_per_query"],
                        per_page=az["results_per_page"], max_days_old=az["max_days_old"],
                        delay=az["delay_seconds"]),
                ))
        else:
            skipped["adzuna"] = {"status": "skipped", "error": "ADZUNA_APP_ID/ADZUNA_APP_KEY not set"}

    for ats, fetcher in ATS_FETCHERS.items():
        for board in cfg.get(ats) or []:
            name = f"{ats}:{board['token']}"
            units.append(Unit(name, name, lambda f=fetcher, b=board: f(client, b["token"], b["company"])))

    if only:
        units = [u for u in units if u.name.startswith(only)]
        skipped = {k: v for k, v in skipped.items() if k.startswith(only)}
    return units, skipped


def ingest_unit(conn: psycopg.Connection, jobs: list[RawJob], seen: set[tuple[str, str]]) -> dict:
    counts = {"fetched": len(jobs), "inserted": 0, "updated": 0, "unchanged": 0,
              "duplicates": 0, "invalid": 0}
    for raw in jobs:
        key = (raw.source_name, raw.source_job_id)
        if key in seen:                       # same record returned twice in this run
            counts["duplicates"] += 1
            continue
        seen.add(key)
        try:
            with conn.transaction():
                outcome = upsert(conn, prepare(raw))
        except psycopg.Error as exc:          # one bad record never sinks the unit
            log.warning("skipping %s/%s: %s", raw.source_name, raw.source_job_id, exc)
            counts["invalid"] += 1
            continue
        if outcome is Outcome.INSERTED:
            counts["inserted"] += 1
        elif outcome is Outcome.UPDATED:
            counts["updated"] += 1
        elif outcome is Outcome.MERGED:
            counts["duplicates"] += 1
        else:
            counts["unchanged"] += 1
    conn.commit()
    return counts


def run(trigger: str, skip_fetch: bool, skip_classify: bool, only: str | None,
        classify_limit: int | None) -> int:
    settings = get_settings()
    conn = connect(settings.database_url)
    migrate(conn)
    run_id = conn.execute(
        "INSERT INTO pipeline_runs (trigger) VALUES (%s) RETURNING id", (trigger,)
    ).fetchone()["id"]
    conn.commit()
    log.info("pipeline run %s started (trigger=%s)", run_id, trigger)

    stats: dict[str, dict] = {}
    errors: list[dict] = []
    totals = {"fetched": 0, "inserted": 0, "updated": 0, "unchanged": 0, "duplicates": 0}
    classified = class_failed = deactivated = 0
    status = "failed"
    try:
        if not skip_fetch:
            client = PoliteClient(settings.user_agent, timeout=settings.http_timeout)
            units, skipped = build_units(settings, client, only)
            stats.update(skipped)
            for name, s in skipped.items():
                errors.append({"stage": "fetch", "source": name, "error": s["error"]})
            seen: set[tuple[str, str]] = set()
            failed_sources: set[str] = set()
            for unit in units:
                try:
                    jobs = unit.fetch()
                except SourceError as exc:
                    not_found = "404" in str(exc)
                    stats[unit.name] = {"status": "not_found" if not_found else "error",
                                        "error": str(exc)[:500]}
                    if not not_found:
                        failed_sources.add(unit.source_name)
                        errors.append({"stage": "fetch", "source": unit.name, "error": str(exc)[:500]})
                    log.warning("%s: %s", unit.name, exc)
                    continue
                except Exception as exc:  # adapter bug or malformed data: isolate it
                    failed_sources.add(unit.source_name)
                    stats[unit.name] = {"status": "error", "error": repr(exc)[:500]}
                    errors.append({"stage": "fetch", "source": unit.name, "error": repr(exc)[:500]})
                    log.exception("%s crashed", unit.name)
                    continue
                counts = ingest_unit(conn, jobs, seen)
                stats[unit.name] = {"status": "ok", **counts}
                for k in totals:
                    totals[k] += counts[k]
                log.info("%s: %s", unit.name, counts)
            client.close()
            if any(s.get("status") == "ok" for s in stats.values()):
                deactivated = deactivate_stale(conn, sorted(failed_sources))
                conn.commit()

        if not skip_classify:
            try:
                classified, class_failed = classify_pending(conn, settings, run_id, classify_limit)
            except PermanentLLMError as exc:
                errors.append({"stage": "classify", "error": str(exc)[:500]})
                log.error("classification stopped: %s", exc)

        ok_units = [s for s in stats.values() if s.get("status") == "ok"]
        if skip_fetch:
            status = "partial" if errors else "success"
        elif not ok_units:
            status = "failed"
        else:
            status = "partial" if errors else "success"
    except Exception as exc:
        conn.rollback()
        errors.append({"stage": "pipeline", "error": repr(exc)[:500],
                       "trace": traceback.format_exc()[-1500:]})
        log.exception("pipeline crashed")
        status = "failed"
    finally:
        conn.execute(
            """UPDATE pipeline_runs SET completed_at=now(), status=%s, jobs_fetched=%s,
                   jobs_inserted=%s, jobs_updated=%s, jobs_unchanged=%s, duplicates_removed=%s,
                   jobs_deactivated=%s, jobs_classified=%s, classification_failures=%s,
                   source_stats=%s, errors=%s
               WHERE id=%s""",
            (status, totals["fetched"], totals["inserted"], totals["updated"],
             totals["unchanged"], totals["duplicates"], deactivated, classified, class_failed,
             Jsonb(stats), Jsonb(errors), run_id),
        )
        conn.commit()
        conn.close()

    summary = {"run_id": run_id, "status": status, **totals, "deactivated": deactivated,
               "classified": classified, "classification_failures": class_failed,
               "errors": len(errors)}
    print(json.dumps(summary, indent=2))
    return 1 if status == "failed" else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--trigger", default="local", choices=["schedule", "manual", "local"])
    p.add_argument("--skip-fetch", action="store_true")
    p.add_argument("--skip-classify", action="store_true")
    p.add_argument("--only", help="only run source units whose name starts with this")
    p.add_argument("--classify-limit", type=int)
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return run(a.trigger, a.skip_fetch, a.skip_classify, a.only, a.classify_limit)


if __name__ == "__main__":
    sys.exit(main())
