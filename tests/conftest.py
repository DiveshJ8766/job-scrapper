"""Test helpers. DB tests use TEST_DATABASE_URL and are skipped when it is not set.

All JSON under tests/fixtures is hand-written in the documented shape of each
public API and exists only for unit tests; it is never loaded by the app.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeClient:
    """Stands in for PoliteClient: returns a fixture for any URL containing a key."""

    def __init__(self, routes: dict[str, object]):
        self.routes = routes
        self.calls: list[tuple[str, dict | None]] = []

    def get_json(self, url, params=None, min_interval=None):
        self.calls.append((url, params))
        for key, value in self.routes.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected URL {url}")


@pytest.fixture
def db():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    from pipeline.db import connect, migrate

    conn = connect(url)
    conn.execute("DROP TABLE IF EXISTS classification_logs, pipeline_runs, job_sources, jobs, "
                 "schema_migrations CASCADE")
    conn.commit()
    migrate(conn)
    yield conn
    conn.close()
