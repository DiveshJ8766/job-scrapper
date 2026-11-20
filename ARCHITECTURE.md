# Architecture

## Overview

```
                ┌──────────────────────── GitHub Actions ─────────────────────────┐
 daily cron ───▶│  daily-refresh.yml  ──▶  python -m pipeline.run                │
 /admin button ─┤  (workflow_dispatch)      1. fetch      one unit per source    │
  via API       │                           2. normalize  RawJob, content_hash   │
                │                           3. dedupe     idempotent upsert      │
                │                           4. deactivate unseen for 3 days      │
                │                           5. classify   new / changed only     │
                │                           6. record     pipeline_runs row      │
                └──────────────────────────────┬───────────────────────────────────┘
                                               │ SQL (psycopg)
                                               ▼
                                     PostgreSQL (Neon)
                                               ▲
                                               │ Drizzle ORM (postgres-js)
                ┌──────────────────────────────┴───────────────────────────────────┐
                │ Next.js 16 on Vercel                                           │
                │  /api/jobs  /api/jobs/:id  /api/filters  /api/stats            │
                │  /api/admin/refresh  ──▶ GitHub API: dispatch daily-refresh.yml │
                │  /  (search, filters, pagination)  /jobs/:id  /admin            │
                └───────────────────────────────────────────────────────────────────┘
```

**Why two languages, and no separate backend service.** Data collection and LLM calls are
batch jobs, so they run in Python on GitHub Actions on a schedule. Serving is request/response,
so it runs in Next.js route handlers on Vercel. The only thing the two share is the database.
A FastAPI service would add hosting, deploys and a network hop without giving either side
anything it lacks.

**Why the admin refresh goes through GitHub.** Vercel functions can't run the Python
pipeline, and runs can take longer than a function timeout. `POST /api/admin/refresh` checks
the admin token and asks GitHub to start the same workflow the cron uses. Everything about a
run (logs, concurrency, retries) then stays in one place.

## Repository layout

| Path | What |
|---|---|
| `db/migrations/*.sql` | Schema, the single source of truth. Applied in order by `python -m pipeline.db`, recorded in `schema_migrations`. |
| `pipeline/sources/` | One adapter per source. `http.py` is the polite HTTP client. |
| `pipeline/normalize.py`, `pipeline/cities.py` | URL canonicalization, company/title normalization, city aliases. |
| `pipeline/ingest.py` | Deduplicating upsert and stale-job deactivation. |
| `pipeline/classify/` | Prompt, schema, LLM clients, pricing, classification loop. |
| `pipeline/run.py` | Orchestrator and CLI. `pipeline/probe.py` checks configured company boards. |
| `lib/` | Server-only DB access (`db/`, `queries.ts`), Zod validation, shared types and constants. |
| `app/api/` | Route handlers. `app/page.tsx`, `app/jobs/[id]`, `app/admin` are the UI. |
| `evaluation/` | 50-post sampling, scoring, cost report. |
| `tests/` | Pytest suite (unit tests plus DB tests against a real Postgres). |

## Database schema

`jobs`: one row per distinct opening.

- Raw fields from the displayed source: `title`, `company`, `description` (plain text),
  `location_raw`, `employment_type_raw`, `application_url`, `posted_at`.
- LLM fields: `role`, `job_type`, `experience_level` (all limited by CHECK constraints to the
  fixed lists), `cities text[]` (normalized, may include `Remote` / `Unknown`), `city` (first
  entry, for display), `is_remote`.
- Provenance: `source_name`, `source_job_id` of the displayed record. Every merged record is
  kept in `job_sources`.
- Dedup keys: `canonical_url` (UNIQUE), `dedupe_key` (indexed, normalized company|title|location).
- Change tracking: `content_hash` (SHA-256 of every field the classifier reads), `classified_hash`
  (the hash that was last classified), `classification_status` (pending | classified | failed),
  `classification_model`, `prompt_version`, `classified_at`, `classification_attempts`.
- Lifecycle: `first_seen_at`, `last_seen_at`, `is_active`.
- `search tsvector`: generated column (title weight A, company B, description C) with a GIN index.

Indexes cover every filter: role, job_type, experience_level, GIN on cities, GIN on search,
plus `(is_active, posted_at DESC, id DESC)` for the default sort.

`job_sources`: every source record seen, `UNIQUE (source_name, source_job_id)`, FK to jobs.

`pipeline_runs`: one row per run, covering status (running | success | partial | failed),
trigger, counts (fetched, inserted, updated, unchanged, duplicates_removed, deactivated,
classified, classification_failures), `source_stats` (per-unit JSON) and `errors` (JSON list).

`classification_logs`: one row per LLM attempt, covering model, prompt version, status
(success | invalid_output | api_error), attempt number, input/output tokens, estimated cost,
latency, the raw and post-processed result, and any error.

## Data flow in detail

### 1. Fetch
`build_units()` turns `pipeline/sources.json` into units: one per Adzuna query and one per company
board. Each unit runs inside its own try/except. Outcomes:

- `ok`: counts recorded.
- `not_found` (HTTP 404, the board doesn't exist): recorded but not treated as an error.
- `error` (timeouts, 5xx after retries, malformed payloads, adapter bugs): recorded in `errors`,
  and the source is added to `failed_sources` so its jobs aren't deactivated this run.

The HTTP client sends an identifying User-Agent, waits at least 1 s between requests (2.5 s for
Adzuna), retries 429/5xx up to 3 times with exponential backoff, and honours `Retry-After`.

### 2. Normalize
Adapters return `RawJob` (Pydantic; title, company, URL and id must not be blank). HTML is converted
to text (Greenhouse sends entity-escaped HTML). ATS boards are filtered to India: the location
mentions India, a known Indian city, or the country code is IN. Word boundaries keep "Indiana"
from matching.

### 3. Deduplicate (see `pipeline/ingest.py`)
Each record is matched in order:

1. **Same `(source_name, source_job_id)` seen before**: same job. The last-seen time is
   refreshed, and if this is the displayed record and its `content_hash` changed, the content is
   updated and the job goes back to `pending`.
2. **Same canonical URL**: duplicate. Canonicalization lowercases the host, drops `www.`, the
   fragment, trailing slashes and tracking parameters (`utm_*`, `gh_src`, `lever-source`, `ref`, ...),
   and keeps identifying parameters such as `gh_jid`. Adzuna redirect URLs are reduced to their
   path (`/jobs/land/ad/<id>`).
3. **Same `dedupe_key`**: duplicate, but only when (a) the records come from different sources
   or one is an aggregator, and (b) the location part is known. Two same-titled postings on one
   company's own board have different ids, so they are different openings and never merged.
   Different cities produce different keys.

When a direct employer posting matches an Adzuna copy, the employer posting becomes the displayed
record (better link, full description). Both stay in `job_sources`.

**Idempotency.** All writes are upserts keyed on unique constraints, so re-running with the same
input changes only `last_seen_at`. The tests run identical input twice and assert zero new
rows. A record repeated within one run (Adzuna often returns the same ad for several queries)
is counted once.

### 4. Deactivate
After fetching, jobs not seen for 3 days are marked `is_active = false`, except those tied to a
source that failed in this run. If a job reappears, it is reactivated.

### 5. Classify (see `PROMPTS.md`)
Selects active jobs that are `pending`, `failed` with fewer than 3 attempts, or classified with
an older `PROMPT_VERSION`. Unchanged jobs are never sent again. Per job: up to 3 attempts.
Transient errors (429, 5xx, network) back off and retry. Invalid output gets one repair prompt.
Permanent errors (400/401/403) fail that job, and 3 permanent errors in a row stop
classification for the run (almost always a bad key or model name). Requests are spaced to
`LLM_MAX_RPM`, and each job is committed separately so progress survives a crash.

### 6. Record
The `pipeline_runs` row is always completed in a `finally` block, so a crash still leaves a
`failed` row with the error and traceback. The process exits non-zero only when the whole run
failed, which turns the Actions run red.

## Error handling summary

| Failure | Behaviour |
|---|---|
| One board or query fails | Recorded in `errors`/`source_stats`; other units continue; status `partial` |
| Board doesn't exist (404) | `not_found` in `source_stats`; not an error |
| Malformed record | Pydantic rejects it in the adapter, or the DB insert is rolled back to a savepoint; counted as `invalid` |
| Every source fails | Status `failed`, exit code 1 (Actions shows red) |
| LLM 429/5xx/timeout | Backoff and retry, max 3 attempts; then `failed`, retried next run (max 3 runs) |
| LLM returns bad JSON | One repair prompt; logged as `invalid_output` |
| Bad LLM key | Stops classification after 3 consecutive permanent errors; ingestion results are kept |
| Missing Adzuna/LLM keys | That stage is skipped and the reason recorded |
| DB down (web) | API returns 500 with a generic message; UI shows an error state with retry |
| Bad query params | 400 with Zod issues |

## Security

- Every secret lives in environment variables (`.env` locally, Vercel and GitHub secrets in
  production). None has a `NEXT_PUBLIC_` prefix, and DB access is in `server-only` modules.
- The admin endpoint compares tokens in constant time. The GitHub token never leaves the server.
- Workflow inputs pass through env vars, never interpolated into shell scripts.
- Outbound links use `rel="noopener noreferrer"`.
