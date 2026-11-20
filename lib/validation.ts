import { z } from "zod";
import { EXPERIENCE_LEVELS, JOB_TYPES, PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX, ROLES } from "./constants";

const optionalEnum = <T extends readonly [string, ...string[]]>(values: T) =>
  z.preprocess((v) => (v === "" || v === null ? undefined : v), z.enum(values).optional());

export const jobsQuerySchema = z.object({
  q: z.preprocess(
    (v) => (typeof v === "string" ? v.trim() || undefined : undefined),
    z.string().max(100).optional(),
  ),
  role: optionalEnum(ROLES),
  city: z.preprocess(
    (v) => (typeof v === "string" ? v.trim() || undefined : undefined),
    z.string().max(60).optional(),
  ),
  jobType: optionalEnum(JOB_TYPES),
  experience: optionalEnum(EXPERIENCE_LEVELS),
  page: z.coerce.number().int().min(1).max(10_000).default(1),
  pageSize: z.coerce.number().int().min(1).max(PAGE_SIZE_MAX).default(PAGE_SIZE_DEFAULT),
});

export type JobsQuery = z.infer<typeof jobsQuerySchema>;

export function parseJobsQuery(params: URLSearchParams) {
  return jobsQuerySchema.safeParse({
    q: params.get("q"),
    role: params.get("role"),
    city: params.get("city"),
    jobType: params.get("jobType"),
    experience: params.get("experience"),
    page: params.get("page") ?? undefined,
    pageSize: params.get("pageSize") ?? undefined,
  });
}

export const jobIdSchema = z.coerce.number().int().positive().max(Number.MAX_SAFE_INTEGER);
