import "server-only";
import { and, count, desc, eq, inArray, isNotNull, sql, type SQL } from "drizzle-orm";
import { getDb, schema } from "./db";
import type {
  FacetValue,
  FiltersResponse,
  JobDetail,
  JobsResponse,
  JobSummary,
  RunSummary,
  StatsResponse,
} from "./types";
import type { JobsQuery } from "./validation";

const { jobs, jobSources, pipelineRuns, classificationLogs } = schema;

const iso = (d: Date | null) => (d ? d.toISOString() : null);

const summaryColumns = {
  id: jobs.id,
  title: jobs.title,
  company: jobs.company,
  city: jobs.city,
  cities: jobs.cities,
  isRemote: jobs.isRemote,
  role: jobs.role,
  jobType: jobs.jobType,
  experienceLevel: jobs.experienceLevel,
  locationRaw: jobs.locationRaw,
  applicationUrl: jobs.applicationUrl,
  sourceName: jobs.sourceName,
  postedAt: jobs.postedAt,
  firstSeenAt: jobs.firstSeenAt,
  classificationStatus: jobs.classificationStatus,
  isActive: jobs.isActive,
};

type SummaryRow = { postedAt: Date | null; firstSeenAt: Date } & Omit<JobSummary, "postedAt" | "firstSeenAt">;

function toSummary(r: SummaryRow): JobSummary {
  return { ...r, postedAt: iso(r.postedAt), firstSeenAt: r.firstSeenAt.toISOString() };
}

export async function listJobs(q: JobsQuery): Promise<JobsResponse> {
  const db = getDb();
  const where: SQL[] = [eq(jobs.isActive, true)];
  if (q.q) {
    const like = `%${q.q.replace(/[\\%_]/g, (c) => `\\${c}`)}%`;
    where.push(sql`(${jobs.search} @@ websearch_to_tsquery('english', ${q.q})
                    OR ${jobs.title} ILIKE ${like} OR ${jobs.company} ILIKE ${like})`);
  }
  if (q.role) where.push(eq(jobs.role, q.role));
  if (q.jobType) where.push(eq(jobs.jobType, q.jobType));
  if (q.experience) where.push(eq(jobs.experienceLevel, q.experience));
  if (q.city) where.push(sql`${jobs.cities} @> ARRAY[${q.city}]::text[]`);
  const filter = and(...where);

  const [rows, [{ total }]] = await Promise.all([
    db
      .select(summaryColumns)
      .from(jobs)
      .where(filter)
      .orderBy(sql`COALESCE(${jobs.postedAt}, ${jobs.firstSeenAt}) DESC`, desc(jobs.id))
      .limit(q.pageSize)
      .offset((q.page - 1) * q.pageSize),
    db.select({ total: count() }).from(jobs).where(filter),
  ]);

  return {
    data: rows.map(toSummary),
    pagination: {
      page: q.page,
      pageSize: q.pageSize,
      total,
      totalPages: Math.max(1, Math.ceil(total / q.pageSize)),
    },
  };
}

export async function getJob(id: number): Promise<JobDetail | null> {
  const db = getDb();
  const [row] = await db
    .select({
      ...summaryColumns,
      description: jobs.description,
      employmentTypeRaw: jobs.employmentTypeRaw,
      classificationModel: jobs.classificationModel,
      classifiedAt: jobs.classifiedAt,
    })
    .from(jobs)
    .where(eq(jobs.id, id));
  if (!row) return null;
  const sources = await db
    .select({
      sourceName: jobSources.sourceName,
      sourceUrl: jobSources.sourceUrl,
      firstSeenAt: jobSources.firstSeenAt,
      lastSeenAt: jobSources.lastSeenAt,
    })
    .from(jobSources)
    .where(eq(jobSources.jobId, id))
    .orderBy(jobSources.firstSeenAt);
  return {
    ...toSummary(row),
    description: row.description,
    employmentTypeRaw: row.employmentTypeRaw,
    classificationModel: row.classificationModel,
    classifiedAt: iso(row.classifiedAt),
    sources: sources.map((s) => ({
      ...s,
      firstSeenAt: s.firstSeenAt.toISOString(),
      lastSeenAt: s.lastSeenAt.toISOString(),
    })),
  };
}

async function facet(column: typeof jobs.role | typeof jobs.jobType | typeof jobs.experienceLevel): Promise<FacetValue[]> {
  const db = getDb();
  const rows = await db
    .select({ value: column, count: count() })
    .from(jobs)
    .where(and(eq(jobs.isActive, true), isNotNull(column)))
    .groupBy(column)
    .orderBy(desc(count()));
  return rows.map((r) => ({ value: r.value as string, count: r.count }));
}

export async function getFilters(): Promise<FiltersResponse> {
  const db = getDb();
  const [roles, jobTypes, experienceLevels, cityRows] = await Promise.all([
    facet(jobs.role),
    facet(jobs.jobType),
    facet(jobs.experienceLevel),
    db.execute<{ value: string; count: string }>(sql`
      SELECT c AS value, count(*) AS count
        FROM jobs, unnest(cities) AS c
       WHERE is_active
       GROUP BY c ORDER BY count(*) DESC, c`),
  ]);
  return {
    roles,
    jobTypes,
    experienceLevels,
    cities: [...cityRows].map((r) => ({ value: r.value, count: Number(r.count) })),
  };
}

const runColumns = {
  id: pipelineRuns.id,
  status: pipelineRuns.status,
  trigger: pipelineRuns.trigger,
  startedAt: pipelineRuns.startedAt,
  completedAt: pipelineRuns.completedAt,
  jobsFetched: pipelineRuns.jobsFetched,
  jobsInserted: pipelineRuns.jobsInserted,
  duplicatesRemoved: pipelineRuns.duplicatesRemoved,
  jobsClassified: pipelineRuns.jobsClassified,
};

function toRun(r: (Omit<RunSummary, "startedAt" | "completedAt"> & { startedAt: Date; completedAt: Date | null }) | undefined): RunSummary | null {
  if (!r) return null;
  return { ...r, startedAt: r.startedAt.toISOString(), completedAt: iso(r.completedAt) };
}

export async function getLastSuccessfulRun(): Promise<RunSummary | null> {
  const db = getDb();
  const [r] = await db
    .select(runColumns)
    .from(pipelineRuns)
    .where(and(inArray(pipelineRuns.status, ["success", "partial"]), isNotNull(pipelineRuns.completedAt)))
    .orderBy(desc(pipelineRuns.completedAt))
    .limit(1);
  return toRun(r);
}

export async function getLatestRun(): Promise<RunSummary | null> {
  const db = getDb();
  const [r] = await db.select(runColumns).from(pipelineRuns).orderBy(desc(pipelineRuns.startedAt)).limit(1);
  return toRun(r);
}

export async function getStats(): Promise<StatsResponse> {
  const db = getDb();
  const [[totals], statusRows, sourceRows, [llm], models, lastSuccessfulRun, lastRun] = await Promise.all([
    db
      .select({ activeJobs: count(), companies: sql<number>`count(DISTINCT lower(${jobs.company}))::int` })
      .from(jobs)
      .where(eq(jobs.isActive, true)),
    db
      .select({ status: jobs.classificationStatus, n: count() })
      .from(jobs)
      .where(eq(jobs.isActive, true))
      .groupBy(jobs.classificationStatus),
    db.execute<{ value: string; count: string }>(sql`
      SELECT split_part(source_name, ':', 1) AS value, count(*) AS count
        FROM jobs WHERE is_active GROUP BY 1 ORDER BY 2 DESC`),
    db
      .select({
        requests: count(),
        inputTokens: sql<number>`coalesce(sum(${classificationLogs.inputTokens}), 0)::bigint`,
        outputTokens: sql<number>`coalesce(sum(${classificationLogs.outputTokens}), 0)::bigint`,
        totalCost: sql<string>`coalesce(sum(${classificationLogs.estimatedCost}), 0)`,
        jobsClassified: sql<number>`count(DISTINCT ${classificationLogs.jobId}) FILTER (WHERE ${classificationLogs.status} = 'success')::int`,
      })
      .from(classificationLogs),
    db.selectDistinct({ m: classificationLogs.modelName }).from(classificationLogs),
    getLastSuccessfulRun(),
    getLatestRun(),
  ]);
  const byStatus = Object.fromEntries(statusRows.map((r) => [r.status, r.n]));
  const totalCost = Number(llm.totalCost);
  const avg = llm.jobsClassified > 0 ? totalCost / llm.jobsClassified : null;
  return {
    activeJobs: totals.activeJobs,
    companies: Number(totals.companies),
    classification: {
      classified: byStatus.classified ?? 0,
      pending: byStatus.pending ?? 0,
      failed: byStatus.failed ?? 0,
    },
    sources: [...sourceRows].map((r) => ({ value: r.value, count: Number(r.count) })),
    lastSuccessfulRun,
    lastRun,
    llm: {
      requests: llm.requests,
      inputTokens: Number(llm.inputTokens),
      outputTokens: Number(llm.outputTokens),
      totalCostUsd: totalCost,
      jobsClassified: llm.jobsClassified,
      avgCostPerJobUsd: avg,
      costPer1000JobsUsd: avg === null ? null : avg * 1000,
      models: models.map((m) => m.m),
    },
  };
}

export interface RunDetail {
  id: number;
  status: string;
  trigger: string;
  startedAt: string;
  completedAt: string | null;
  jobsFetched: number;
  jobsInserted: number;
  duplicatesRemoved: number;
  jobsClassified: number;
  errors: { stage: string; source?: string; error: string }[];
}

export async function getRecentRuns(limit: number): Promise<RunDetail[]> {
  const db = getDb();
  const rows = await db
    .select({ ...runColumns, errors: pipelineRuns.errors })
    .from(pipelineRuns)
    .orderBy(desc(pipelineRuns.startedAt))
    .limit(limit);
  return rows.map((r) => ({
    ...r,
    startedAt: r.startedAt.toISOString(),
    completedAt: iso(r.completedAt),
    errors: Array.isArray(r.errors) ? (r.errors as RunDetail["errors"]) : [],
  }));
}
