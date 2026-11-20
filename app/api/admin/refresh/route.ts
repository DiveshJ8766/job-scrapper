import { timingSafeEqual } from "node:crypto";
import type { NextRequest } from "next/server";
import { error, json } from "@/lib/http";
import { getLatestRun } from "@/lib/queries";

// The pipeline is Python and runs in GitHub Actions, so a manual refresh dispatches the
// same workflow the daily cron uses. Secrets stay server-side; the browser only sends
// the admin token it was given.

function tokenMatches(given: string, expected: string) {
  const a = Buffer.from(given);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

const RUNNING_WINDOW_MS = 30 * 60 * 1000;

export async function POST(request: NextRequest) {
  const expected = process.env.ADMIN_REFRESH_TOKEN;
  const ghToken = process.env.GITHUB_DISPATCH_TOKEN;
  const repo = process.env.GITHUB_REPO;
  if (!expected || !ghToken || !repo) {
    return error(503, "Manual refresh is not configured on this deployment.");
  }

  const auth = request.headers.get("authorization") ?? "";
  const given = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!given || !tokenMatches(given, expected)) return error(401, "Invalid admin token");

  try {
    const latest = await getLatestRun();
    if (
      latest?.status === "running" &&
      Date.now() - new Date(latest.startedAt).getTime() < RUNNING_WINDOW_MS
    ) {
      return error(409, `A refresh is already running (run #${latest.id}).`);
    }
  } catch (err) {
    console.error("[api] refresh: could not read pipeline_runs", err);
  }

  const workflow = process.env.GITHUB_WORKFLOW_FILE || "daily-refresh.yml";
  const ref = process.env.GITHUB_REF_NAME || "main";
  const res = await fetch(
    `https://api.github.com/repos/${repo}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${ghToken}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref, inputs: { trigger: "manual" } }),
      cache: "no-store",
    },
  );
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    console.error(`[api] refresh: GitHub dispatch failed ${res.status}: ${detail.slice(0, 300)}`);
    return error(502, `GitHub refused to start the workflow (HTTP ${res.status}).`);
  }
  return json(
    { ok: true, message: "Refresh started. New data appears when the workflow finishes (usually 10-30 minutes)." },
    { status: 202 },
  );
}
