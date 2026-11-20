import json

import pytest

from pipeline.classify import classifier as clf
from pipeline.classify.llm import LLMResponse, PermanentLLMError, TransientLLMError
from pipeline.classify.prompt import PROMPT_VERSION, build_user_prompt, MAX_DESCRIPTION_CHARS
from pipeline.ingest import prepare, upsert
from pipeline.models import RawJob

GOOD = {"role": "Frontend Developer", "cities": ["Bangalore", "Chennai"], "is_remote": False,
        "job_type": "Full-time", "experience_level": "Fresher", "confidence": "high"}


class FakeLLM:
    model = "fake-model"

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.prompts = []

    def complete_json(self, system, user):
        self.prompts.append(user)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return LLMResponse(out if isinstance(out, str) else json.dumps(out), 900, 40, 120)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(clf.time, "sleep", lambda s: None)


def test_parse_rejects_unknown_role_and_extra_keys():
    with pytest.raises(clf.InvalidOutput):
        clf.parse_output(json.dumps({**GOOD, "role": "Wizard"}))
    with pytest.raises(clf.InvalidOutput):
        clf.parse_output(json.dumps({**GOOD, "salary": "10 LPA"}))
    with pytest.raises(clf.InvalidOutput):
        clf.parse_output("not json")


def test_parse_accepts_code_fence():
    assert clf.parse_output("```json\n" + json.dumps(GOOD) + "\n```").role == "Frontend Developer"


def test_postprocess_normalizes_and_drops_hallucinated_city():
    out = clf.parse_output(json.dumps(GOOD))
    final = clf.postprocess(out, title="React Dev", location_raw="Bangalore, India",
                            description="Great team")
    assert final.cities == ["Bengaluru"]
    assert final.city == "Bengaluru"
    assert final.dropped_cities == ["Chennai"]


def test_postprocess_unknown_and_remote():
    out = clf.parse_output(json.dumps({**GOOD, "cities": [], "is_remote": True}))
    final = clf.postprocess(out, title="Dev", location_raw="Remote - India", description=None)
    assert final.cities == ["Remote"] and final.is_remote
    out = clf.parse_output(json.dumps({**GOOD, "cities": [], "is_remote": True}))
    final = clf.postprocess(out, title="Dev", location_raw="India", description="Office based")
    assert final.cities == ["Unknown"] and not final.is_remote


def test_prompt_truncates_long_descriptions():
    p = build_user_prompt("T", "C", None, None, "x" * (MAX_DESCRIPTION_CHARS + 50))
    assert "(truncated)" in p and "Location (as listed): not listed" in p


def _seed(db):
    upsert(db, prepare(RawJob(source_name="greenhouse:acme", source_job_id="1",
                              title="Frontend Engineer", company="Acme",
                              application_url="https://x.io/1", location_raw="Bangalore",
                              description="React, 0-1 years")))
    return clf.select_jobs_to_classify(db, 10)[0]


def test_classify_job_success_logs_tokens_and_cost(db):
    job = _seed(db)
    final = clf.classify_job(db, FakeLLM([GOOD]), job, None)
    assert final.cities == ["Bengaluru"]
    row = db.execute("SELECT * FROM jobs").fetchone()
    assert row["classification_status"] == "classified"
    assert row["role"] == "Frontend Developer" and row["classification_model"] == "fake-model"
    assert row["prompt_version"] == PROMPT_VERSION and row["classified_at"] is not None
    log = db.execute("SELECT * FROM classification_logs").fetchone()
    assert (log["input_tokens"], log["output_tokens"], log["status"]) == (900, 40, "success")
    # unchanged job is not selected again
    assert clf.select_jobs_to_classify(db, 10) == []


def test_invalid_then_repaired(db):
    job = _seed(db)
    llm = FakeLLM(["{oops", GOOD])
    assert clf.classify_job(db, llm, job, None) is not None
    assert "previous answer was rejected" in llm.prompts[1]
    statuses = [r["status"] for r in db.execute("SELECT status FROM classification_logs ORDER BY id")]
    assert statuses == ["invalid_output", "success"]


def test_transient_errors_retry_then_fail(db):
    job = _seed(db)
    llm = FakeLLM([TransientLLMError("429")] * 3)
    assert clf.classify_job(db, llm, job, None) is None
    row = db.execute("SELECT classification_status, classification_attempts FROM jobs").fetchone()
    assert row["classification_status"] == "failed" and row["classification_attempts"] == 1
    # failed jobs are retried on a later run until the attempt cap
    assert len(clf.select_jobs_to_classify(db, 10)) == 1


def test_permanent_error_propagates(db):
    job = _seed(db)
    with pytest.raises(PermanentLLMError):
        clf.classify_job(db, FakeLLM([PermanentLLMError("401")]), job, None)
