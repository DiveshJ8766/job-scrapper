import "server-only";
import type { ApiError } from "./types";

// Data refreshes once a day, so a short CDN cache is safe and keeps the database quiet.
export const PUBLIC_CACHE = "public, s-maxage=120, stale-while-revalidate=600";

export function json<T>(body: T, init: ResponseInit & { cache?: string } = {}) {
  const headers = new Headers(init.headers);
  headers.set("Cache-Control", init.cache ?? "no-store");
  return Response.json(body, { ...init, headers });
}

export function error(status: number, message: string, details?: unknown) {
  const body: ApiError = details === undefined ? { error: message } : { error: message, details };
  return json(body, { status });
}

export function serverError(where: string, err: unknown) {
  console.error(`[api] ${where} failed:`, err);
  return error(500, "Something went wrong while reading jobs. Please try again.");
}
