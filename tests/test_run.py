import os

from pipeline import run as runmod
from pipeline.models import RawJob
from pipeline.sources.http import SourceError


def _job(i, src="greenhouse:acme"):
    return RawJob(source_name=src, source_job_id=str(i), title=f"Engineer {i}", company="Acme",
                  application_url=f"https://boards.greenhouse.io/acme/jobs/{i}",
                  location_raw="Pune", description="desc")


def _boom():
    raise RuntimeError("adapter bug")


def _missing():
    raise SourceError("https://x: 404 Not Found (board or endpoint does not exist)")


def test_one_failing_source_does_not_stop_run(db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    units = [
        runmod.Unit("greenhouse:acme", "greenhouse:acme", lambda: [_job(1), _job(2), _job(2)]),
        runmod.Unit("lever:broken", "lever:broken", _boom),
        runmod.Unit("ashby:gone", "ashby:gone", _missing),
    ]
    monkeypatch.setattr(runmod, "build_units", lambda s, c, o: (units, {}))

    assert runmod.run("local", False, True, None, None) == 0
    r = db.execute("SELECT * FROM pipeline_runs ORDER BY id DESC").fetchone()
    assert r["status"] == "partial"
    assert (r["jobs_fetched"], r["jobs_inserted"], r["duplicates_removed"]) == (3, 2, 1)
    assert r["source_stats"]["lever:broken"]["status"] == "error"
    assert r["source_stats"]["ashby:gone"]["status"] == "not_found"
    assert len(r["errors"]) == 1 and r["completed_at"] is not None

    # second identical run inserts nothing
    assert runmod.run("local", False, True, None, None) == 0
    r2 = db.execute("SELECT * FROM pipeline_runs ORDER BY id DESC").fetchone()
    assert (r2["jobs_inserted"], r2["jobs_unchanged"]) == (0, 2)
    assert db.execute("SELECT count(*) n FROM jobs").fetchone()["n"] == 2


def test_all_sources_failing_marks_run_failed(db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.setattr(runmod, "build_units",
                        lambda s, c, o: ([runmod.Unit("lever:broken", "lever:broken", _boom)], {}))
    assert runmod.run("local", False, True, None, None) == 1
    assert db.execute("SELECT status FROM pipeline_runs").fetchone()["status"] == "failed"
