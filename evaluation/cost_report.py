"""Cost analysis from logged token usage (classification_logs).

    python -m evaluation.cost_report            # prints markdown, writes evaluation/cost_report.md
"""

from __future__ import annotations

import sys
from pathlib import Path

from pipeline.classify.pricing import PRICING_DATE, price_for
from pipeline.db import connect

HERE = Path(__file__).parent


def main() -> int:
    with connect() as conn:
        per_model = conn.execute(
            """SELECT model_name,
                      count(*) AS requests,
                      count(*) FILTER (WHERE status='success') AS successes,
                      count(*) FILTER (WHERE status<>'success') AS failed_attempts,
                      count(DISTINCT job_id) FILTER (WHERE status='success') AS jobs,
                      coalesce(sum(input_tokens),0) AS tin, coalesce(sum(output_tokens),0) AS tout,
                      coalesce(sum(estimated_cost),0) AS cost,
                      min(created_at) AS first_at, max(created_at) AS last_at
                 FROM classification_logs GROUP BY model_name ORDER BY model_name"""
        ).fetchall()
    if not per_model:
        print("No classification_logs yet. Run the pipeline with an LLM key first.")
        return 1

    lines = [f"# LLM cost report", "", f"List prices as of {PRICING_DATE} (see pipeline/classify/pricing.py).", ""]
    lines += ["| Model | Price in/out per 1M | Jobs classified | Requests (incl. retries) | Input tokens | Output tokens | Total cost | Avg / job | Per 1,000 jobs |",
              "|---|---|---|---|---|---|---|---|---|"]
    for m in per_model:
        price = price_for(m["model_name"])
        jobs = m["jobs"] or 0
        cost = float(m["cost"])
        avg = cost / jobs if jobs else None
        lines.append(
            f"| {m['model_name']} | {'$%.2f / $%.2f' % price if price else 'unpriced'} | {jobs} | {m['requests']} | "
            f"{m['tin']:,} | {m['tout']:,} | ${cost:.6f} | "
            f"{'$%.8f' % avg if avg is not None else '—'} | {'$%.4f' % (avg * 1000) if avg is not None else '—'} |")
        if jobs:
            lines.append("")
            lines.append(f"Average tokens per classified job ({m['model_name']}): "
                         f"{m['tin'] / jobs:,.0f} input, {m['tout'] / jobs:,.1f} output. "
                         f"Failed attempts included in cost: {m['failed_attempts']}. "
                         f"Period: {m['first_at']:%Y-%m-%d} to {m['last_at']:%Y-%m-%d}.")
    text = "\n".join(lines) + "\n"
    (HERE / "cost_report.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
