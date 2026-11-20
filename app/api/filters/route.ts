import { connection } from "next/server";
import { json, PUBLIC_CACHE, serverError } from "@/lib/http";
import { getFilters } from "@/lib/queries";

export async function GET() {
  await connection(); // always read live data, never prerender at build time
  try {
    return json(await getFilters(), { cache: PUBLIC_CACHE });
  } catch (err) {
    return serverError("GET /api/filters", err);
  }
}
