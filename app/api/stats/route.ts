import { connection } from "next/server";
import { json, PUBLIC_CACHE, serverError } from "@/lib/http";
import { getStats } from "@/lib/queries";

export async function GET() {
  await connection();
  try {
    return json(await getStats(), { cache: PUBLIC_CACHE });
  } catch (err) {
    return serverError("GET /api/stats", err);
  }
}
