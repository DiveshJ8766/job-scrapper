import "server-only";
import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

declare global {
  var __pg: ReturnType<typeof postgres> | undefined;
}

function client() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not set");
  // prepare:false keeps us compatible with transaction-mode poolers (Neon pooled URLs).
  // One small pool per serverless instance; reused across hot reloads in dev.
  globalThis.__pg ??= postgres(url, { prepare: false, max: 3, idle_timeout: 20 });
  return globalThis.__pg;
}

export function getDb() {
  return drizzle(client(), { schema });
}

export { schema };
