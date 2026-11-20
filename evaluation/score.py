"""Step 2 of the evaluation: score LLM predictions against human-verified labels.

    python -m evaluation.score                      # reads evaluation/eval_set.csv
    python -m evaluation.score --csv path/to/file.csv

Refuses to produce numbers while any verified_role / verified_cities cell is blank,
so results can never include made-up labels.

Outputs (next to the CSV):
  eval_results.json          headline metrics
  confusion_matrix.csv       role confusion matrix (rows = verified, cols = predicted)
  eval_report.md             readable report to paste into EVALUATION.md

City labels: semicolon-separated city names; use "Remote" for remote and "Unknown"
when the posting gives no city. Names are normalized (Bangalore -> Bengaluru).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pipeline.cities import canonical_city
from pipeline.classify.schema import ROLES

HERE = Path(__file__).parent


def norm_cities(cell: str) -> frozenset[str]:
    out = set()
    for part in cell.replace(",", ";").split(";"):
        p = part.strip()
        if not p:
            continue
        if p.lower() in {"remote", "work from home", "wfh"}:
            out.add("Remote")
        elif p.lower() in {"unknown", "n/a", "none", "-"}:
            out.add("Unknown")
        else:
            out.add(canonical_city(p) or p.title())
    return frozenset(out or {"Unknown"})


def norm_role(cell: str) -> str | None:
    c = cell.strip().lower()
    for r in ROLES:
        if r.lower() == c:
            return r
    return None


def load(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def validate(rows: list[dict]) -> list[str]:
    problems = []
    for i, r in enumerate(rows, start=2):
        if not r["verified_role"].strip():
            problems.append(f"row {i} (job {r['job_id']}): verified_role is empty")
        elif norm_role(r["verified_role"]) is None:
            problems.append(f"row {i} (job {r['job_id']}): verified_role {r['verified_role']!r} "
                            f"is not one of the allowed roles")
        if not r["verified_cities"].strip():
            problems.append(f"row {i} (job {r['job_id']}): verified_cities is empty "
                            f"(write Unknown if the posting has no city)")
    return problems


def score(rows: list[dict]) -> dict:
    n = len(rows)
    role_ok = city_exact = city_overlap = 0
    confusion: Counter[tuple[str, str]] = Counter()
    mistakes, ambiguous, unknown = [], [], []
    for r in rows:
        vr, pr = norm_role(r["verified_role"]), r["predicted_role"].strip()
        vc, pc = norm_cities(r["verified_cities"]), norm_cities(r["predicted_cities"])
        confusion[(vr, pr)] += 1
        r_ok, c_ok = vr == pr, vc == pc
        role_ok += r_ok
        city_exact += c_ok
        city_overlap += bool(vc & pc)
        item = {"job_id": r["job_id"], "title": r["title"], "company": r["company"],
                "location_raw": r["location_raw"],
                "role": {"verified": vr, "predicted": pr},
                "cities": {"verified": sorted(vc), "predicted": sorted(pc)},
                "llm_confidence": r.get("llm_confidence", ""), "notes": r.get("notes", "")}
        if not (r_ok and c_ok):
            mistakes.append(item)
        if r.get("is_ambiguous", "").strip().lower() in {"yes", "y", "true", "1"}:
            ambiguous.append(item)
        if "Unknown" in (vr, pr) or "Unknown" in vc or "Unknown" in pc:
            unknown.append(item)
    labels = [x for x in ROLES if any(x in k for k in confusion)]
    return {
        "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n": n,
        "role_accuracy": role_ok / n,
        "role_correct": role_ok,
        "city_exact_accuracy": city_exact / n,
        "city_exact_correct": city_exact,
        "city_any_overlap_accuracy": city_overlap / n,
        "models": sorted({r.get("classification_model", "") for r in rows}),
        "confusion_labels": labels,
        "confusion": {f"{a}|||{b}": c for (a, b), c in confusion.items()},
        "mistakes": mistakes,
        "ambiguous": ambiguous,
        "unknown_cases": unknown,
    }


def write_outputs(res: dict, out_dir: Path) -> None:
    (out_dir / "eval_results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    labels = res["confusion_labels"]
    conf = {tuple(k.split("|||")): v for k, v in res["confusion"].items()}
    with (out_dir / "confusion_matrix.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["verified \\ predicted", *labels])
        for a in labels:
            w.writerow([a, *[conf.get((a, b), 0) for b in labels]])

    pct = lambda x: f"{x * 100:.1f}%"  # noqa: E731
    md = [
        f"# Evaluation results ({res['n']} manually verified postings)",
        "",
        f"Scored {res['scored_at']} · model(s): {', '.join(res['models'])}",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Role accuracy | {pct(res['role_accuracy'])} ({res['role_correct']}/{res['n']}) |",
        f"| City accuracy (exact set match) | {pct(res['city_exact_accuracy'])} ({res['city_exact_correct']}/{res['n']}) |",
        f"| City accuracy (at least one city matches) | {pct(res['city_any_overlap_accuracy'])} |",
        "",
        "## Role confusion matrix (rows = verified, columns = predicted)",
        "",
        "| verified \\ predicted | " + " | ".join(labels) + " |",
        "|---|" + "---|" * len(labels),
    ]
    for a in labels:
        md.append(f"| **{a}** | " + " | ".join(str(conf.get((a, b), 0) or "·") for b in labels) + " |")

    def section(title: str, items: list[dict]) -> None:
        md.extend(["", f"## {title} ({len(items)})", ""])
        if not items:
            md.append("None.")
            return
        md.append("| Job | Title | Location (raw) | Role verified → predicted | Cities verified → predicted | Notes |")
        md.append("|---|---|---|---|---|---|")
        for m in items:
            md.append(f"| {m['job_id']} | {m['title']} ({m['company']}) | {m['location_raw']} | "
                      f"{m['role']['verified']} → {m['role']['predicted']} | "
                      f"{'; '.join(m['cities']['verified'])} → {'; '.join(m['cities']['predicted'])} | {m['notes']} |")

    section("Errors", res["mistakes"])
    section("Ambiguous cases (flagged by the reviewer)", res["ambiguous"])
    section("Unknown cases", res["unknown_cases"])
    (out_dir / "eval_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(HERE / "eval_set.csv"))
    a = ap.parse_args(argv)
    path = Path(a.csv)
    rows = load(path)
    if not rows:
        print("CSV has no rows.")
        return 1
    problems = validate(rows)
    if problems:
        print("Cannot score yet - fill in the verified labels first:")
        print("\n".join(f"  - {p}" for p in problems[:30]))
        if len(problems) > 30:
            print(f"  ... and {len(problems) - 30} more")
        return 1
    res = score(rows)
    write_outputs(res, path.parent)
    print(f"Role accuracy: {res['role_accuracy']:.1%}  City accuracy (exact): {res['city_exact_accuracy']:.1%}")
    print(f"Wrote eval_results.json, confusion_matrix.csv, eval_report.md to {path.parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
