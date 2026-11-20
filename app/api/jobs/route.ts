import type { NextRequest } from "next/server";
import { error, json, PUBLIC_CACHE, serverError } from "@/lib/http";
import { listJobs } from "@/lib/queries";
import { parseJobsQuery } from "@/lib/validation";

export async function GET(request: NextRequest) {
  const parsed = parseJobsQuery(request.nextUrl.searchParams);
  if (!parsed.success) return error(400, "Invalid query parameters", parsed.error.issues);
  try {
    return json(await listJobs(parsed.data), { cache: PUBLIC_CACHE });
  } catch (err) {
    return serverError("GET /api/jobs", err);
  }
}
