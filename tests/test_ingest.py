from datetime import datetime, timezone

from pipeline.ingest import Outcome, deactivate_stale, prepare, upsert
from pipeline.models import RawJob


def raw(**kw) -> RawJob:
    base = dict(source_name="greenhouse:acme", source_job_id="1", title="Software Engineer",
                company="Acme Pvt Ltd", application_url="https://boards.greenhouse.io/acme/jobs/1",
                description="Build things", location_raw="Bangalore, India",
                posted_at=datetime(2026, 11, 1, tzinfo=timezone.utc))
    base.update(kw)
    return RawJob(**base)


def count(conn, table="jobs"):
    return conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]


def test_insert_then_rerun_is_idempotent(db):
    assert upsert(db, prepare(raw())) is Outcome.INSERTED
    assert upsert(db, prepare(raw())) is Outcome.UNCHANGED
    assert count(db) == 1 and count(db, "job_sources") == 1


def test_content_change_marks_pending_again(db):
    upsert(db, prepare(raw()))
    db.execute("UPDATE jobs SET classification_status='classified', classified_hash=content_hash")
    assert upsert(db, prepare(raw(description="Build different things"))) is Outcome.UPDATED
    assert db.execute("SELECT classification_status FROM jobs").fetchone()["classification_status"] == "pending"


def test_unchanged_content_keeps_classification(db):
    upsert(db, prepare(raw()))
    db.execute("UPDATE jobs SET classification_status='classified', classified_hash=content_hash")
    upsert(db, prepare(raw()))
    assert db.execute("SELECT classification_status FROM jobs").fetchone()["classification_status"] == "classified"


def test_same_url_with_tracking_params_is_duplicate(db):
    upsert(db, prepare(raw()))
    dup = raw(source_name="lever:acme", source_job_id="x",
              application_url="https://www.boards.greenhouse.io/acme/jobs/1/?utm_source=li")
    assert upsert(db, prepare(dup)) is Outcome.MERGED
    assert count(db) == 1 and count(db, "job_sources") == 2


def test_aggregator_copy_merges_and_direct_posting_wins(db):
    agg = raw(source_name="adzuna", source_job_id="az1", company="ACME",
              application_url="https://www.adzuna.in/jobs/land/ad/az1", location_raw="Bengaluru")
    assert upsert(db, prepare(agg)) is Outcome.INSERTED
    assert upsert(db, prepare(raw())) is Outcome.MERGED
    row = db.execute("SELECT source_name, application_url FROM jobs").fetchone()
    assert row["source_name"] == "greenhouse:acme"
    assert "greenhouse" in row["application_url"]
    assert count(db, "job_sources") == 2
    # re-running both is still idempotent
    assert upsert(db, prepare(agg)) is Outcome.UNCHANGED
    assert upsert(db, prepare(raw())) is Outcome.UNCHANGED
    assert count(db) == 1


def test_same_title_on_same_board_is_not_merged(db):
    upsert(db, prepare(raw()))
    other = raw(source_job_id="2", application_url="https://boards.greenhouse.io/acme/jobs/2")
    assert upsert(db, prepare(other)) is Outcome.INSERTED
    assert count(db) == 2


def test_different_city_is_not_merged(db):
    upsert(db, prepare(raw()))
    other = raw(source_name="lever:acme", source_job_id="z", location_raw="Pune",
                application_url="https://jobs.lever.co/acme/z")
    assert upsert(db, prepare(other)) is Outcome.INSERTED


def test_unknown_location_never_secondary_merged(db):
    upsert(db, prepare(raw(location_raw=None)))
    other = raw(source_name="lever:acme", source_job_id="z", location_raw=None,
                application_url="https://jobs.lever.co/acme/z")
    assert upsert(db, prepare(other)) is Outcome.INSERTED


def test_deactivate_respects_failed_sources(db):
    upsert(db, prepare(raw()))
    upsert(db, prepare(raw(source_name="adzuna", source_job_id="a", title="Data Analyst",
                           application_url="https://adzuna.in/jobs/land/ad/a")))
    db.execute("UPDATE jobs SET last_seen_at = now() - interval '5 days'")
    assert deactivate_stale(db, ["adzuna"]) == 1
    active = db.execute("SELECT source_name FROM jobs WHERE is_active").fetchall()
    assert [r["source_name"] for r in active] == ["adzuna"]
    # seeing it again reactivates it
    upsert(db, prepare(raw()))
    assert db.execute("SELECT count(*) n FROM jobs WHERE is_active").fetchone()["n"] == 2
