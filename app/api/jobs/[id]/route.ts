import type { NextRequest } from "next/server";
import { error, json, PUBLIC_CACHE, serverError } from "@/lib/http";
import { getJob } from "@/lib/queries";
import { jobIdSchema } from "@/lib/validation";

export async function GET(_req: NextRequest, ctx: RouteContext<"/api/jobs/[id]">) {
  const { id } = await ctx.params;
  const parsed = jobIdSchema.safeParse(id);
  if (!parsed.success) return error(400, "Job id must be a positive integer");
  try {
    const job = await getJob(parsed.data);
    if (!job) return error(404, "Job not found");
    return json({ data: job }, { cache: PUBLIC_CACHE });
  } catch (err) {
    return serverError("GET /api/jobs/:id", err);
  }
}
