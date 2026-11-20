# Cost analysis

> **Status: estimate only.** Real token counts don't exist until the pipeline runs with an LLM
> key. Every number in "Measured results" must come from `python -m evaluation.cost_report`,
> which reads the tokens logged for each request in `classification_logs`.

## How cost is tracked

- Every LLM attempt (including retries and failures) writes a `classification_logs` row with
  `input_tokens` and `output_tokens` as reported by the provider (`usageMetadata` for Gemini,
  `usage` for OpenAI; Gemini thinking tokens count as output because they're billed as output).
- `estimated_cost = input_tokens × input_price + output_tokens × output_price`, using the list
  prices in `pipeline/classify/pricing.py`, overridable with `LLM_PRICE_INPUT_PER_M` /
  `LLM_PRICE_OUTPUT_PER_M`.
- **Average cost per job** = total cost of all attempts ÷ number of distinct jobs classified
  successfully. Failed attempts are included, so retries aren't hidden.
- **Cost per 1,000 jobs** = average cost per job × 1,000.
- `/admin` and `GET /api/stats` show these figures live. `python -m evaluation.cost_report`
  writes them as markdown.

## Pricing used

Checked **2026-11-20**. Gemini figures come from Google's official pricing page; prices change,
so re-check before quoting.

| Model | Input / 1M tokens | Output / 1M tokens | Source |
|---|---|---|---|
| `gemini-2.5-flash-lite` (default) | $0.10 | $0.40 | aistudio.google.com/docs/pricing, Standard paid tier |
| `gemini-3.1-flash-lite` | $0.25 | $1.50 | same |
| `gemini-2.5-flash` | $0.30 | $2.50 | same |
| `gpt-4o-mini` | $0.15 | $0.60 | **Not confirmed** on OpenAI's official page on the pricing date. Verify before relying on it |

Gemini's free tier charges $0 within its rate limits. The figures here show what the same
usage costs on the paid tier, which is what matters for scaling.

## Pre-run estimate (to be replaced by measured numbers)

Prompt sizes measured from the code, at roughly 4 characters per token:

| Part | Approx. tokens |
|---|---|
| System prompt | ~750 |
| User message, Adzuna job (short snippet) | ~150–250 |
| User message, ATS job (description cut at 4,000 chars) | up to ~1,050 |
| Output (one small JSON object) | ~40–60 |

With `gemini-2.5-flash-lite`:

| Case | Input | Output | Cost per job | Per 1,000 jobs |
|---|---|---|---|---|
| Adzuna job | ~1,000 | ~50 | ~$0.00012 | ~$0.12 |
| Long ATS job | ~1,800 | ~50 | ~$0.00020 | ~$0.20 |

**Estimated: about $0.12–$0.20 per 1,000 jobs.** Because unchanged jobs are never reclassified,
the daily cost scales with *new or changed* postings, not the total.

## Measured results

_Pending. Paste the output of `python -m evaluation.cost_report` here after the first real run._

## Infrastructure costs (kept separate from LLM cost)

| Component | Plan | Cost | Notes |
|---|---|---|---|
| Vercel (Next.js) | Hobby | $0 | Hobby is for non-commercial use; a commercial deployment needs Pro |
| Postgres (Neon via Vercel Marketplace) | Free | $0 | This dataset (about 1,000–5,000 rows) is far below free-tier storage |
| GitHub Actions | Free minutes | $0 | Public repos get free Actions minutes; private repos get a monthly allowance |
| Adzuna, Greenhouse, Lever, Ashby APIs | Free | $0 | Within documented free usage |
| **LLM** | pay-as-you-go | see above | The only cost that grows with volume |

Plan limits and prices for Vercel, Neon and GitHub change often. Check them when deploying.

## Assumptions

- About 4 characters per token for the estimate. Measured numbers replace it.
- Descriptions are cut at 4,000 characters before classification.
- Prices are list prices, without batch or caching discounts. The batch API would roughly halve
  them but delays results.
