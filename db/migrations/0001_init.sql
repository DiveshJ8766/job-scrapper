-- FresherJobs AI: initial schema.
-- This SQL file is the single source of truth for the database schema.
-- The Python pipeline writes with plain SQL; the Next.js app reads through
-- Drizzle (lib/db/schema.ts mirrors these tables).

CREATE TABLE IF NOT EXISTS jobs (
  id                     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  title                  TEXT NOT NULL CHECK (length(trim(title)) > 0),
  company                TEXT NOT NULL CHECK (length(trim(company)) > 0),
  description            TEXT,
  location_raw           TEXT,
  employment_type_raw    TEXT,

  -- LLM classification output
  city                   TEXT,                        -- primary city (first of cities)
  cities                 TEXT[] NOT NULL DEFAULT '{}',-- all normalized cities, may include 'Remote'
  is_remote              BOOLEAN NOT NULL DEFAULT FALSE,
  role                   TEXT CHECK (role IN (
                           'Frontend Developer','Backend Developer','Full Stack Developer',
                           'Software Engineer','Data Analyst','Data Scientist',
                           'Machine Learning Engineer','AI Engineer','DevOps Engineer',
                           'QA Engineer','UI UX Designer','Product Manager','Other','Unknown')),
  job_type               TEXT CHECK (job_type IN (
                           'Full-time','Part-time','Internship','Contract','Temporary','Unknown')),
  experience_level       TEXT CHECK (experience_level IN (
                           'Internship','Fresher','Junior','Mid','Senior','Unknown')),

  -- provenance
  application_url        TEXT NOT NULL,
  canonical_url          TEXT NOT NULL UNIQUE,
  source_name            TEXT NOT NULL,               -- source of the record currently displayed
  source_job_id          TEXT,
  dedupe_key             TEXT NOT NULL,               -- normalized company|title|location

  posted_at              TIMESTAMPTZ,
  first_seen_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  is_active              BOOLEAN NOT NULL DEFAULT TRUE,

  -- change detection / classification bookkeeping
  content_hash           TEXT NOT NULL,
  classification_status  TEXT NOT NULL DEFAULT 'pending'
                           CHECK (classification_status IN ('pending','classified','failed')),
  classified_hash        TEXT,                        -- content_hash at time of last successful classification
  classification_model   TEXT,
  prompt_version         TEXT,
  classified_at          TIMESTAMPTZ,
  classification_attempts INT NOT NULL DEFAULT 0,

  search                 TSVECTOR GENERATED ALWAYS AS (
                           setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                           setweight(to_tsvector('english', coalesce(company, '')), 'B') ||
                           setweight(to_tsvector('english', coalesce(description, '')), 'C')
                         ) STORED,

  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS jobs_dedupe_key_idx      ON jobs (dedupe_key);
CREATE INDEX IF NOT EXISTS jobs_active_posted_idx   ON jobs (is_active, posted_at DESC NULLS LAST, id DESC);
CREATE INDEX IF NOT EXISTS jobs_role_idx            ON jobs (role);
CREATE INDEX IF NOT EXISTS jobs_job_type_idx        ON jobs (job_type);
CREATE INDEX IF NOT EXISTS jobs_experience_idx      ON jobs (experience_level);
CREATE INDEX IF NOT EXISTS jobs_cities_gin_idx      ON jobs USING GIN (cities);
CREATE INDEX IF NOT EXISTS jobs_search_gin_idx      ON jobs USING GIN (search);
CREATE INDEX IF NOT EXISTS jobs_status_idx          ON jobs (classification_status);

-- Every source record that was merged into a job. Keeps original provenance
-- even when the same opening appears on several sources.
CREATE TABLE IF NOT EXISTS job_sources (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id          BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  source_name     TEXT NOT NULL,
  source_job_id   TEXT NOT NULL,
  source_url      TEXT NOT NULL,
  first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_name, source_job_id)
);
CREATE INDEX IF NOT EXISTS job_sources_job_idx ON job_sources (job_id);

CREATE TABLE IF NOT EXISTS pipeline_runs (
  id                       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  started_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at             TIMESTAMPTZ,
  status                   TEXT NOT NULL DEFAULT 'running'
                             CHECK (status IN ('running','success','partial','failed')),
  trigger                  TEXT NOT NULL DEFAULT 'manual',  -- schedule | manual | local
  jobs_fetched             INT NOT NULL DEFAULT 0,
  jobs_inserted            INT NOT NULL DEFAULT 0,
  jobs_updated             INT NOT NULL DEFAULT 0,
  jobs_unchanged           INT NOT NULL DEFAULT 0,
  duplicates_removed       INT NOT NULL DEFAULT 0,
  jobs_deactivated         INT NOT NULL DEFAULT 0,
  jobs_classified          INT NOT NULL DEFAULT 0,
  classification_failures  INT NOT NULL DEFAULT 0,
  source_stats             JSONB NOT NULL DEFAULT '{}'::jsonb,
  errors                   JSONB NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX IF NOT EXISTS pipeline_runs_started_idx ON pipeline_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS classification_logs (
  id                     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id                 BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  pipeline_run_id        BIGINT REFERENCES pipeline_runs(id) ON DELETE SET NULL,
  model_name             TEXT NOT NULL,
  prompt_version         TEXT NOT NULL,
  status                 TEXT NOT NULL CHECK (status IN ('success','invalid_output','api_error')),
  attempt                INT NOT NULL DEFAULT 1,
  input_tokens           INT NOT NULL DEFAULT 0,
  output_tokens          INT NOT NULL DEFAULT 0,
  estimated_cost         NUMERIC(14, 8) NOT NULL DEFAULT 0,
  latency_ms             INT,
  classification_result  JSONB,
  error                  TEXT,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS classification_logs_job_idx ON classification_logs (job_id);
CREATE INDEX IF NOT EXISTS classification_logs_created_idx ON classification_logs (created_at DESC);
