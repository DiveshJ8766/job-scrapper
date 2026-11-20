// Read-side mirror of db/migrations/0001_init.sql (the SQL file is the source of truth;
// the Python pipeline owns migrations and writes).
import {
  bigint,
  boolean,
  customType,
  integer,
  jsonb,
  numeric,
  pgTable,
  text,
  timestamp,
} from "drizzle-orm/pg-core";

const tsvector = customType<{ data: string }>({ dataType: () => "tsvector" });
const ts = (name: string) => timestamp(name, { withTimezone: true, mode: "date" });

export const jobs = pgTable("jobs", {
  id: bigint("id", { mode: "number" }).primaryKey(),
  title: text("title").notNull(),
  company: text("company").notNull(),
  description: text("description"),
  locationRaw: text("location_raw"),
  employmentTypeRaw: text("employment_type_raw"),
  city: text("city"),
  cities: text("cities").array().notNull(),
  isRemote: boolean("is_remote").notNull(),
  role: text("role"),
  jobType: text("job_type"),
  experienceLevel: text("experience_level"),
  applicationUrl: text("application_url").notNull(),
  canonicalUrl: text("canonical_url").notNull(),
  sourceName: text("source_name").notNull(),
  sourceJobId: text("source_job_id"),
  dedupeKey: text("dedupe_key").notNull(),
  postedAt: ts("posted_at"),
  firstSeenAt: ts("first_seen_at").notNull(),
  lastSeenAt: ts("last_seen_at").notNull(),
  isActive: boolean("is_active").notNull(),
  contentHash: text("content_hash").notNull(),
  classificationStatus: text("classification_status").notNull(),
  classificationModel: text("classification_model"),
  promptVersion: text("prompt_version"),
  classifiedAt: ts("classified_at"),
  search: tsvector("search"),
  createdAt: ts("created_at").notNull(),
  updatedAt: ts("updated_at").notNull(),
});

export const jobSources = pgTable("job_sources", {
  id: bigint("id", { mode: "number" }).primaryKey(),
  jobId: bigint("job_id", { mode: "number" }).notNull(),
  sourceName: text("source_name").notNull(),
  sourceJobId: text("source_job_id").notNull(),
  sourceUrl: text("source_url").notNull(),
  firstSeenAt: ts("first_seen_at").notNull(),
  lastSeenAt: ts("last_seen_at").notNull(),
});

export const pipelineRuns = pgTable("pipeline_runs", {
  id: bigint("id", { mode: "number" }).primaryKey(),
  startedAt: ts("started_at").notNull(),
  completedAt: ts("completed_at"),
  status: text("status").notNull(),
  trigger: text("trigger").notNull(),
  jobsFetched: integer("jobs_fetched").notNull(),
  jobsInserted: integer("jobs_inserted").notNull(),
  jobsUpdated: integer("jobs_updated").notNull(),
  jobsUnchanged: integer("jobs_unchanged").notNull(),
  duplicatesRemoved: integer("duplicates_removed").notNull(),
  jobsDeactivated: integer("jobs_deactivated").notNull(),
  jobsClassified: integer("jobs_classified").notNull(),
  classificationFailures: integer("classification_failures").notNull(),
  sourceStats: jsonb("source_stats").notNull(),
  errors: jsonb("errors").notNull(),
});

export const classificationLogs = pgTable("classification_logs", {
  id: bigint("id", { mode: "number" }).primaryKey(),
  jobId: bigint("job_id", { mode: "number" }).notNull(),
  modelName: text("model_name").notNull(),
  promptVersion: text("prompt_version").notNull(),
  status: text("status").notNull(),
  inputTokens: integer("input_tokens").notNull(),
  outputTokens: integer("output_tokens").notNull(),
  estimatedCost: numeric("estimated_cost").notNull(),
  createdAt: ts("created_at").notNull(),
});
