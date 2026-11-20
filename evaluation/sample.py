"""Step 1 of the evaluation: draw a reproducible random sample of classified jobs.

    python -m evaluation.sample                 # 50 jobs, seed "beep-eval-1"
    python -m evaluation.sample --n 50 --seed my-seed --out evaluation/eval_set.csv

The CSV has empty verified_* columns. A person fills them in by reading each
posting (the original link is included), then runs `python -m evaluation.score`.
Sampling is deterministic for a given seed and database state (ORDER BY md5(seed || id)).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from pipeline.db import connect

HERE = Path(__file__).parent
COLUMNS = [
    "job_id", "title", "company", "location_raw", "employment_type_raw", "description_excerpt",
    "application_url", "source_name",
    "predicted_role", "predicted_cities", "predicted_job_type", "predicted_experience",
    "llm_confidence", "classification_model",
    "verified_role", "verified_cities", "is_ambiguous", "notes",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", default="beep-eval-1")
    ap.add_argument("--out", default=str(HERE / "eval_set.csv"))
    a = ap.parse_args(argv)

    out = Path(a.out)
    if out.exists():
        print(f"{out} already exists; refusing to overwrite labels. Use --out for a new file.")
        return 1

    with connect() as conn:
        rows = conn.execute(
            """SELECT j.id, j.title, j.company, j.location_raw, j.employment_type_raw,
                      left(regexp_replace(coalesce(j.description, ''), '\\s+', ' ', 'g'), 600) AS excerpt,
                      j.application_url, j.source_name, j.role, j.cities, j.job_type,
                      j.experience_level, j.classification_model,
                      (SELECT l.classification_result->'llm'->>'confidence'
                         FROM classification_logs l
                        WHERE l.job_id = j.id AND l.status = 'success'
                        ORDER BY l.id DESC LIMIT 1) AS confidence
                 FROM jobs j
                WHERE j.classification_status = 'classified'
                ORDER BY md5(%s || j.id::text)
                LIMIT %s""",
            (a.seed, a.n),
        ).fetchall()

    if len(rows) < a.n:
        print(f"Only {len(rows)} classified jobs available (wanted {a.n}). Run the pipeline first.")
        if not rows:
            return 1

    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow([
                r["id"], r["title"], r["company"], r["location_raw"] or "", r["employment_type_raw"] or "",
                r["excerpt"], r["application_url"], r["source_name"],
                r["role"], "; ".join(r["cities"]), r["job_type"], r["experience_level"],
                r["confidence"] or "", r["classification_model"],
                "", "", "", "",
            ])
    print(f"Wrote {len(rows)} rows to {out} (seed={a.seed!r}). Fill verified_role, verified_cities, "
          f"is_ambiguous (yes/no) and notes, then run: python -m evaluation.score")
    return 0


if __name__ == "__main__":
    sys.exit(main())
