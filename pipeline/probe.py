"""Check every configured company board: does it exist, and how many India jobs does it have?

    python -m pipeline.probe            # prints a table, writes nothing to the database
"""

from __future__ import annotations

import json
import sys

from .config import get_settings
from .run import SOURCES_FILE
from .sources.ats import ATS_FETCHERS
from .sources.http import PoliteClient, SourceError


def main() -> int:
    settings = get_settings()
    cfg = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    client = PoliteClient(settings.user_agent, timeout=settings.http_timeout, max_retries=2)
    rows = []
    for ats, fetcher in ATS_FETCHERS.items():
        for b in cfg.get(ats) or []:
            try:
                n = len(fetcher(client, b["token"], b["company"]))
                rows.append((f"{ats}:{b['token']}", "ok", n))
            except SourceError as exc:
                rows.append((f"{ats}:{b['token']}", "404" if "404" in str(exc) else "error", 0))
    client.close()
    width = max(len(r[0]) for r in rows) if rows else 10
    print(f"{'board'.ljust(width)}  status  india_jobs")
    for name, status, n in sorted(rows, key=lambda r: -r[2]):
        print(f"{name.ljust(width)}  {status.ljust(6)}  {n}")
    print(f"\nTotal India jobs across working boards: {sum(r[2] for r in rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
