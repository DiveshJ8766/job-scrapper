# FresherJobs AI

An AI-powered aggregator of tech job and internship openings in India. Every day it collects
postings from public job APIs, removes duplicates, uses an LLM to label each posting with
**role, city, job type and experience level**, and serves them in a searchable web app.

- **Web:** Next.js 16 (App Router, TypeScript), Drizzle ORM, Zod, Tailwind CSS. Deployed on Vercel.
- **Pipeline:** Python 3.12 (httpx, Pydantic, psycopg 3), run daily by GitHub Actions.
- **Database:** PostgreSQL (Neon recommended).
- **LLM:** Gemini `gemini-2.5-flash-lite` by default (OpenAI supported), structured JSON output.

| Doc | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design, schema, data flow, deduplication, error handling |
| [DATA_SOURCES.md](DATA_SOURCES.md) | Every source, its terms, field mapping |
| [PROMPTS.md](PROMPTS.md) | The exact LLM prompts and output schema |
| [EVALUATION.md](EVALUATION.md) | 50-post manual evaluation method and results |
| [COST_ANALYSIS.md](COST_ANALYSIS.md) | Token tracking, cost per job and per 1,000 jobs, infrastructure costs |

## Current status

| Part | State |
|---|---|
| Schema, migrations, deduplication, idempotent upserts | Built; tested against real Postgres |
| Source adapters (Adzuna, Greenhouse, Lever, Ashby) | Built and fixture-tested. ATS adapters **verified live** on GitHub Actions on 2026-11-20: 24 boards, 957 India jobs. Adzuna is untested until its key is added |
| LLM classification, validation, retries, cost logging | Built; tested with a mocked provider. **Not yet run against a live LLM** |
| API routes and UI | Built; tested end to end on a local Postgres |
| GitHub Actions (daily, manual, CI) | Written and YAML-validated; **runs once secrets are added** |
| 200+ real jobs, evaluation results, measured costs | **Pending the first real run** (see "First real run" below) |

## Local setup

Requirements: Node 22+, Python 3.12+, a Postgres database (local or Neon).

```bash
git clone https://github.com/DiveshJ8766/job-scrapper.git
cd job-scrapper
cp .env.example .env          # then fill in the values (see comments in the file)

npm install
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

python -m pipeline.db         # create tables
python -m pipeline.run        # fetch + dedupe + classify (needs keys in .env)
npm run dev                   # http://localhost:3000
```

Useful commands:

```bash
python -m pipeline.run --skip-classify        # ingest only
python -m pipeline.run --skip-fetch           # classify pending jobs only
python -m pipeline.run --only greenhouse      # one source family
python -m pipeline.probe                      # which company boards exist and how many India jobs each has
python -m pytest -q                           # tests (DB tests need TEST_DATABASE_URL)
npm run typecheck && npm run lint && npm run build
```

## Environment variables

All variables are documented in [.env.example](.env.example). Locally they're read from `.env`
(git-ignored) by both Next.js and the Python pipeline.

| Variable | Used by | Required |
|---|---|---|
| `DATABASE_URL` | web + pipeline | yes |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | pipeline | for Adzuna (main volume source) |
| `LLM_PROVIDER`, `LLM_MODEL`, `GEMINI_API_KEY` / `OPENAI_API_KEY` | pipeline | for classification |
| `ADMIN_REFRESH_TOKEN`, `GITHUB_DISPATCH_TOKEN`, `GITHUB_REPO` | web | for the /admin refresh button |

None use the `NEXT_PUBLIC_` prefix, so no key can be bundled into frontend code.

## Deployment

### 1. Database
Create a Postgres database. The easiest route is **Vercel dashboard → Storage → Neon** (free tier),
connected to this project. Copy its **pooled** connection string.

### 2. Vercel (web app)
1. Import `DiveshJ8766/job-scrapper` in Vercel (framework detected as Next.js, no settings to change).
2. In Project → Settings → Environment Variables, add `DATABASE_URL`, `ADMIN_REFRESH_TOKEN`,
   `GITHUB_DISPATCH_TOKEN`, `GITHUB_REPO=DiveshJ8766/job-scrapper`.
   - `GITHUB_DISPATCH_TOKEN`: a fine-grained personal access token limited to this repository
     with **Actions: Read and write**.
3. Deploy.

### 3. GitHub Actions (daily pipeline)
In the repo, go to **Settings → Secrets and variables → Actions**:
- Secrets: `DATABASE_URL`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `GEMINI_API_KEY` (or `OPENAI_API_KEY`).
- Variables (optional): `LLM_PROVIDER`, `LLM_MODEL`, `LLM_MAX_RPM`, `LLM_MAX_JOBS_PER_RUN`.

The `Daily job refresh` workflow runs at 06:47 IST every day. It applies migrations on its
own, so the first run also creates the tables.

### 4. First real run
1. (Optional) Actions → **Probe company boards** → Run workflow to re-check the board list.
2. Actions → **Daily job refresh** → Run workflow. Check the job summary (fetched / inserted /
   duplicates / classified) and that `/` shows 200+ jobs.
3. Open `/admin` to see run status and LLM cost.
4. Run the evaluation (see [EVALUATION.md](EVALUATION.md)) and the cost report
   (`python -m evaluation.cost_report`), then paste the results into the two docs.

## API

| Endpoint | Description |
|---|---|
| `GET /api/jobs?q=&role=&city=&jobType=&experience=&page=&pageSize=` | Paginated active jobs, newest first. `q` uses Postgres full-text search plus title/company substring match. `pageSize` ≤ 50 |
| `GET /api/jobs/:id` | One job with full description and every source it was merged from |
| `GET /api/filters` | Facet values with counts (roles, cities, job types, experience levels) |
| `GET /api/stats` | Totals, classification status, last successful refresh, LLM tokens and cost |
| `POST /api/admin/refresh` | `Authorization: Bearer <ADMIN_REFRESH_TOKEN>`; starts the GitHub Actions pipeline. 202 on success, 401 bad token, 409 already running, 503 not configured |

Invalid parameters return `400` with details. GET responses are cached at the edge for 2 minutes.

## Known limitations

- **Company boards are a curated list** (24 verified on 2026-11-20). Coverage depends on which employers use Greenhouse/Lever/Ashby. Re-run the probe to keep it current.
- **Adzuna snippets.** About 500-character descriptions give the LLM less context. Adzuna links
  go through an Adzuna redirect, not the employer's page.
- **Free-tier LLM rate limits.** With `LLM_MAX_RPM=12`, one run classifies up to about 700 jobs an
  hour. A first run with a large backlog may need two daily runs, or a higher RPM on a paid key.
- **Secondary dedupe is deliberately conservative.** The same job posted by two different
  recruiters on Adzuna with slightly different titles stays as two rows. That's preferred over
  merging different openings by mistake.
- **No user accounts, saved searches or alerts.** Out of scope.
- **Admin auth is one shared token**, enough for a single administrator.
