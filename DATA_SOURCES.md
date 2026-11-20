# Data sources

Only publicly documented APIs that exist to distribute job listings are used. No HTML scraping,
no logins, nothing that gets around a CAPTCHA or anti-bot protection. Configuration lives in
`pipeline/sources.json`.

| Source | Endpoint | Auth | Fields we get | Limits we respect |
|---|---|---|---|---|
| Adzuna (India) | `GET https://api.adzuna.com/v1/api/jobs/in/search/{page}` | `app_id` + `app_key` (free) | id, title, company, location, **description snippet**, created, contract_time/type, category, redirect_url | 15 queries × up to 2 pages × 50 results per day, 2.5 s between requests |
| Greenhouse Job Board API | `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | none for GET | id, title, location, offices, full HTML content, updated_at / first_published, absolute_url | 1 request per board per day |
| Lever Postings API | `GET https://api.lever.co/v0/postings/{site}?mode=json` | none | id, text, categories (location, commitment, allLocations), country, workplaceType, descriptionPlain, lists, createdAt, hostedUrl | 1 request per board per day |
| Ashby Posting API | `GET https://api.ashbyhq.com/posting-api/job-board/{board}` | none | id, title, location(s), employmentType, isRemote, descriptionPlain, publishedAt, jobUrl | 1 request per board per day |

All requests send `User-Agent: FresherJobsAI/1.0 (+repo URL)`, leave at least 1 s between calls,
retry 429/5xx at most 3 times with backoff, and honour `Retry-After`.

## Source notes

### Adzuna
- Aggregator. Most of the volume comes from here: many Indian employers post through job boards
  rather than an ATS with a public API.
- **Attribution.** Adzuna's API terms require a visible "Jobs by Adzuna" label on every listing
  shown from their API. The UI renders it on every Adzuna card and on the detail page
  (`components/AdzunaAttribution.tsx`).
- `redirect_url` goes through Adzuna to the employer's page. That is the link we store and show.
  It is **not** the employer's own URL.
- Descriptions are short snippets (about 500 characters), so classification has less context than
  for ATS jobs. The detail page says so.
- Listings missing a company or title are dropped. Nothing is shown with made-up fields.

### Greenhouse, Lever, Ashby (company career boards)
- These are the employers' own public job boards, read through the documented read-only APIs
  their career pages use. Links point straight at the employer's posting.
- Only India-based postings are kept (location mentions India or an Indian city, or country = IN).
- Company boards are listed in `sources.json`. **Verified 2026-11-20** with the "Probe company boards"
  workflow (GitHub Actions run 44749633192). 24 boards returned India jobs, **957 in total**, led by
  Paytm (192), Okta (105), Zscaler (101), Databricks (77) and MongoDB (70). 18 candidate tokens
  returned 404 or had no India jobs and were removed. Re-run the probe any time; a board that
  disappears shows up as `not_found` and never fails a run.

### Considered and excluded
| Source | Why excluded |
|---|---|
| LinkedIn, Naukri, Indeed, Glassdoor, Foundit, Internshala | No public job-listing API for this use; their terms forbid automated scraping |
| Jooble API | Keys are issued manually on request with tight per-key limits, and it returns snippets only. Could be added later as another aggregator adapter |
| Company HTML career pages | Brittle, and scraping terms vary per site; the ATS APIs above cover the same postings in structured form |

## Field mapping

| Our field | Adzuna | Greenhouse | Lever | Ashby |
|---|---|---|---|---|
| `title` | `title` (HTML stripped) | `title` | `text` | `title` |
| `company` | `company.display_name` | `company_name` or configured name | configured name | configured name |
| `description` | `description` (snippet) | `content` (HTML → text) | `descriptionPlain` + `lists` + `additionalPlain` | `descriptionPlain` |
| `location_raw` | `location.display_name` | `location.name` + office locations | `categories.allLocations` / `location` (+ "(Remote)") | `location` + `secondaryLocations` (+ "(Remote)") |
| `employment_type_raw` | `contract_time`, `contract_type` | employment metadata if exposed | `categories.commitment` | `employmentType` |
| `posted_at` | `created` | `first_published` or `updated_at` | `createdAt` (ms) | `publishedAt` |
| `application_url` | `redirect_url` | `absolute_url` | `hostedUrl` | `jobUrl` |
| `source_job_id` | `id` | `id` | `id` | `id` |

Missing optional fields are stored as NULL and shown as "Not listed". They are never filled in
by guessing.

## Adding a source

1. Write a fetch function that returns `list[RawJob]` and raises `SourceError` on failure
   (see `pipeline/sources/ats.py`).
2. Register it in `build_units()` or `ATS_FETCHERS`.
3. Add a fixture-based test in `tests/test_sources.py`.
4. Document it in this file.
