import pytest

from pipeline.sources.adzuna import fetch_adzuna_query
from pipeline.sources.ats import fetch_ashby, fetch_greenhouse, fetch_lever, is_india_location
from pipeline.sources.http import SourceError

from .conftest import FakeClient, load_fixture


def test_greenhouse_keeps_only_india_and_cleans_html():
    client = FakeClient({"boards-api.greenhouse.io": load_fixture("greenhouse_jobs.json")})
    jobs = fetch_greenhouse(client, "acme", "Acme")
    assert [j.source_job_id for j in jobs] == ["1001"]
    j = jobs[0]
    assert j.source_name == "greenhouse:acme"
    assert j.company == "Acme"
    assert "Join our platform team" in j.description and "<" not in j.description
    assert "Bangalore" in j.location_raw and "Bengaluru" in j.location_raw
    assert j.posted_at is not None
    assert client.calls[0][1] == {"content": "true"}


def test_lever_filters_country_and_merges_lists():
    client = FakeClient({"api.lever.co": load_fixture("lever_postings.json")})
    jobs = fetch_lever(client, "beta", "Beta")
    assert len(jobs) == 1
    j = jobs[0]
    assert j.employment_type_raw == "Internship"
    assert j.location_raw == "Pune, Remote"
    assert "SQL" in j.description and "Requirements" in j.description


def test_ashby_skips_unlisted_and_marks_remote():
    client = FakeClient({"api.ashbyhq.com": load_fixture("ashby_board.json")})
    jobs = fetch_ashby(client, "gamma", "Gamma")
    assert [j.source_job_id for j in jobs] == ["c1"]
    assert jobs[0].location_raw == "Remote - India"


def test_adzuna_drops_incomplete_and_strips_title_html():
    client = FakeClient({"api.adzuna.com": load_fixture("adzuna_page.json")})
    jobs = fetch_adzuna_query(client, "id", "key", country="in", query="frontend", pages=2,
                              per_page=50, max_days_old=30, delay=0)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Junior Frontend Developer"
    assert j.is_aggregator and j.source_name == "adzuna"
    assert j.employment_type_raw == "full time, permanent"
    assert len(client.calls) == 1   # stops paging when a page is short


def test_adapter_raises_source_error_on_bad_shape():
    client = FakeClient({"boards-api.greenhouse.io": {"unexpected": True}})
    with pytest.raises(SourceError):
        fetch_greenhouse(client, "acme", "Acme")


def test_india_location_detection():
    assert is_india_location("Remote, India")
    assert is_india_location("Gurgaon")
    assert not is_india_location("Indianapolis, Indiana")
    assert is_india_location(None, country="IN")
