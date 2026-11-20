"""Database connection and a minimal, ordered SQL migration runner."""

from __future__ import annotations

import sys

import psycopg
from psycopg.rows import dict_row

from .config import REPO_ROOT, get_settings

MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"


def connect(database_url: str | None = None) -> psycopg.Connection:
    url = database_url or get_settings().database_url
    # prepare_threshold=None keeps us compatible with PgBouncer-style poolers (Neon pooled URLs).
    return psycopg.connect(url, row_factory=dict_row, prepare_threshold=None)


def migrate(conn: psycopg.Connection) -> list[str]:
    """Apply every db/migrations/*.sql file not yet recorded. Returns applied names."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    done = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()}
    applied: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in done:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
        applied.append(path.name)
    conn.commit()
    return applied


if __name__ == "__main__":
    with connect() as c:
        names = migrate(c)
    print("Applied:", ", ".join(names) if names else "nothing (up to date)")
    sys.exit(0)
