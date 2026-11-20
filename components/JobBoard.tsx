"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useId, useState } from "react";
import { EXPERIENCE_LEVELS, JOB_TYPES, ROLES } from "@/lib/constants";
import type { FacetValue, FiltersResponse, JobsResponse } from "@/lib/types";
import { JobCard, JobCardSkeleton } from "./JobCard";

type Status = "loading" | "ready" | "error";
const FILTER_KEYS = ["role", "city", "jobType", "experience"] as const;

function withCounts(values: readonly string[], facets: FacetValue[] | undefined) {
  const counts = new Map((facets ?? []).map((f) => [f.value, f.count]));
  return values.map((v) => ({ value: v, count: counts.get(v) }));
}

function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; count?: number }[];
  onChange: (v: string) => void;
}) {
  const id = useId();
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-slate-600">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 w-full rounded-md border border-slate-300 bg-white px-2 text-sm text-slate-900"
      >
        <option value="">All</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.value}
            {o.count !== undefined ? ` (${o.count})` : ""}
          </option>
        ))}
      </select>
    </div>
  );
}

export function JobBoard() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const paramString = params.toString();

  const [filters, setFilters] = useState<FiltersResponse | null>(null);
  // The loaded response remembers which request it answers; "loading" is derived from
  // whether that matches the current URL, so no state is set synchronously in effects.
  const [loaded, setLoaded] = useState<{ key: string; data?: JobsResponse; error?: string } | null>(null);
  const [lastData, setLastData] = useState<JobsResponse | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const requestKey = `${paramString}#${reloadKey}`;
  const status: Status = loaded?.key !== requestKey ? "loading" : loaded.error ? "error" : "ready";
  const result = loaded?.key === requestKey && loaded.data ? loaded.data : lastData;
  const errorMsg = loaded?.error ?? "";
  const [query, setQuery] = useState(params.get("q") ?? "");

  const update = useCallback(
    (changes: Record<string, string | null>, resetPage = true) => {
      const next = new URLSearchParams(paramString);
      for (const [k, v] of Object.entries(changes)) {
        if (v) next.set(k, v);
        else next.delete(k);
      }
      if (resetPage) next.delete("page");
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [paramString, pathname, router],
  );

  // Facets for filter dropdowns.
  useEffect(() => {
    fetch("/api/filters")
      .then((r) => (r.ok ? r.json() : null))
      .then((d: FiltersResponse | null) => d && setFilters(d))
      .catch(() => {});
  }, []);

  // Debounced keyword search.
  useEffect(() => {
    const current = new URLSearchParams(paramString).get("q") ?? "";
    if (query.trim() === current) return;
    const t = setTimeout(() => update({ q: query.trim() || null }), 400);
    return () => clearTimeout(t);
  }, [query, paramString, update]);

  // Jobs for the current URL state.
  useEffect(() => {
    const ctrl = new AbortController();
    const key = `${paramString}#${reloadKey}`;
    fetch(`/api/jobs?${paramString}`, { signal: ctrl.signal })
      .then(async (r) => {
        const body = await r.json().catch(() => null);
        if (!r.ok) throw new Error(body?.error ?? `Request failed (${r.status})`);
        return body as JobsResponse;
      })
      .then((d) => {
        setLoaded({ key, data: d });
        setLastData(d);
      })
      .catch((e: Error) => {
        if (e.name === "AbortError") return;
        setLoaded({ key, error: e.message });
      });
    return () => ctrl.abort();
  }, [paramString, reloadKey]);

  const active = FILTER_KEYS.some((k) => params.get(k)) || !!params.get("q");
  const p = result?.pagination;
  const from = p && p.total > 0 ? (p.page - 1) * p.pageSize + 1 : 0;
  const to = p ? Math.min(p.page * p.pageSize, p.total) : 0;

  return (
    <section aria-labelledby="results-heading" className="flex flex-col gap-5">
      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          update({ q: query.trim() || null });
        }}
        className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs"
      >
        <label htmlFor="q" className="sr-only">
          Search jobs
        </label>
        <div className="flex gap-2">
          <input
            id="q"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            maxLength={100}
            placeholder="Search by title, company or skill — e.g. React, Python, Razorpay"
            className="h-10 min-w-0 flex-1 rounded-md border border-slate-300 px-3 text-sm placeholder:text-slate-400"
          />
          <button type="submit" className="h-10 rounded-md bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-800">
            Search
          </button>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Select label="Role" value={params.get("role") ?? ""} options={withCounts(ROLES, filters?.roles)} onChange={(v) => update({ role: v || null })} />
          <Select label="City" value={params.get("city") ?? ""} options={filters?.cities ?? []} onChange={(v) => update({ city: v || null })} />
          <Select label="Job type" value={params.get("jobType") ?? ""} options={withCounts(JOB_TYPES, filters?.jobTypes)} onChange={(v) => update({ jobType: v || null })} />
          <Select label="Experience" value={params.get("experience") ?? ""} options={withCounts(EXPERIENCE_LEVELS, filters?.experienceLevels)} onChange={(v) => update({ experience: v || null })} />
        </div>
      </form>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="results-heading" className="text-sm text-slate-600" aria-live="polite">
          {status === "ready" && p
            ? p.total === 0
              ? "No jobs match"
              : `Showing ${from}–${to} of ${p.total.toLocaleString("en-IN")} jobs`
            : status === "loading"
              ? "Loading jobs…"
              : "Could not load jobs"}
        </h2>
        {active && (
          <button
            type="button"
            onClick={() => {
              setQuery("");
              router.replace(pathname, { scroll: false });
            }}
            className="text-sm font-medium text-brand-700 hover:underline"
          >
            Clear all filters
          </button>
        )}
      </div>

      {status === "error" && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-5 text-sm text-red-800">
          <p className="font-medium">We couldn&apos;t load jobs right now.</p>
          <p className="mt-1">{errorMsg}</p>
          <button type="button" onClick={() => setReloadKey((k) => k + 1)} className="mt-3 rounded-md border border-red-300 bg-white px-3 py-1.5 font-medium hover:bg-red-100">
            Try again
          </button>
        </div>
      )}

      {status === "loading" && !result && (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 5 }, (_, i) => (
            <JobCardSkeleton key={i} />
          ))}
        </div>
      )}

      {result && status !== "error" && (
        <div className={`flex flex-col gap-3 ${status === "loading" ? "opacity-60" : ""}`} aria-busy={status === "loading"}>
          {result.data.length === 0 && status === "ready" ? (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
              <p className="font-medium text-slate-900">No jobs found</p>
              <p className="mt-1 text-sm text-slate-600">
                {active ? "Try a broader search or remove a filter." : "No jobs have been collected yet. The daily refresh will add them."}
              </p>
            </div>
          ) : (
            result.data.map((job) => <JobCard key={job.id} job={job} />)
          )}
        </div>
      )}

      {p && p.totalPages > 1 && status !== "error" && (
        <nav aria-label="Pagination" className="flex items-center justify-between gap-3 pt-2">
          <button
            type="button"
            disabled={p.page <= 1}
            onClick={() => {
              update({ page: String(p.page - 1) }, false);
              window.scrollTo({ top: 0 });
            }}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            ← Previous
          </button>
          <span className="text-sm text-slate-600">
            Page {p.page} of {p.totalPages}
          </span>
          <button
            type="button"
            disabled={p.page >= p.totalPages}
            onClick={() => {
              update({ page: String(p.page + 1) }, false);
              window.scrollTo({ top: 0 });
            }}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Next →
          </button>
        </nav>
      )}
    </section>
  );
}
