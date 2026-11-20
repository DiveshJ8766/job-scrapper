import { connection } from "next/server";
import { Suspense } from "react";
import { RefreshButton } from "@/components/RefreshButton";
import { pricingNote } from "@/lib/admin";
import { formatDateTime, formatUsd } from "@/lib/format";
import { getRecentRuns, getStats } from "@/lib/queries";

export default function AdminPage() {
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Admin</h1>
        <p className="mt-1 text-sm text-slate-600">Pipeline health, LLM usage and manual refresh.</p>
      </div>
      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-base font-semibold text-slate-900">Manual refresh</h2>
        <p className="mb-4 mt-1 text-sm text-slate-600">
          Starts the same GitHub Actions workflow as the daily schedule: fetch, deduplicate, classify new or changed jobs.
        </p>
        <RefreshButton />
      </section>
      <Suspense fallback={<p className="text-sm text-slate-500">Loading pipeline data…</p>}>
        <AdminData />
      </Suspense>
    </div>
  );
}

async function AdminData() {
  await connection();
  let stats, runs;
  try {
    [stats, runs] = await Promise.all([getStats(), getRecentRuns(10)]);
  } catch (err) {
    console.error("[admin] failed", err);
    return <p role="alert" className="text-sm text-red-700">Could not read pipeline data from the database.</p>;
  }
  const l = stats.llm;
  return (
    <>
      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-base font-semibold text-slate-900">LLM classification cost</h2>
        <dl className="mt-3 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
          <Item k="Jobs classified" v={l.jobsClassified.toLocaleString("en-IN")} />
          <Item k="Requests (incl. retries)" v={l.requests.toLocaleString("en-IN")} />
          <Item k="Input / output tokens" v={`${l.inputTokens.toLocaleString("en-IN")} / ${l.outputTokens.toLocaleString("en-IN")}`} />
          <Item k="Total cost" v={formatUsd(l.totalCostUsd)} />
          <Item k="Avg cost per job" v={formatUsd(l.avgCostPerJobUsd, 6)} />
          <Item k="Est. cost per 1,000 jobs" v={formatUsd(l.costPer1000JobsUsd, 4)} />
          <Item k="Pending / failed" v={`${stats.classification.pending} / ${stats.classification.failed}`} />
          <Item k="Model(s)" v={l.models.join(", ") || "—"} />
        </dl>
        <p className="mt-3 text-xs text-slate-500">{pricingNote}</p>
      </section>
      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-base font-semibold text-slate-900">Recent pipeline runs</h2>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="text-xs text-slate-500">
              <tr>
                <th className="py-2 pr-3 font-medium">Run</th>
                <th className="py-2 pr-3 font-medium">Started</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 font-medium">Fetched</th>
                <th className="py-2 pr-3 font-medium">New</th>
                <th className="py-2 pr-3 font-medium">Duplicates</th>
                <th className="py-2 pr-3 font-medium">Classified</th>
                <th className="py-2 font-medium">Source errors</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {runs.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-4 text-slate-500">No runs recorded yet.</td>
                </tr>
              )}
              {runs.map((r) => (
                <tr key={r.id} className="align-top">
                  <td className="py-2 pr-3">#{r.id} <span className="text-slate-500">({r.trigger})</span></td>
                  <td className="py-2 pr-3">{formatDateTime(r.startedAt)}</td>
                  <td className="py-2 pr-3"><StatusPill status={r.status} /></td>
                  <td className="py-2 pr-3">{r.jobsFetched}</td>
                  <td className="py-2 pr-3">{r.jobsInserted}</td>
                  <td className="py-2 pr-3">{r.duplicatesRemoved}</td>
                  <td className="py-2 pr-3">{r.jobsClassified}</td>
                  <td className="py-2 text-xs text-slate-600">
                    {r.errors.length === 0 ? "—" : r.errors.slice(0, 4).map((e, i) => (
                      <div key={i}>{e.source ?? e.stage}: {e.error.slice(0, 90)}</div>
                    ))}
                    {r.errors.length > 4 && <div>+{r.errors.length - 4} more</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function Item({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{k}</dt>
      <dd className="mt-0.5 font-medium text-slate-900">{v}</dd>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const tone =
    status === "success" ? "bg-emerald-50 text-emerald-800" :
    status === "partial" ? "bg-amber-50 text-amber-800" :
    status === "running" ? "bg-brand-50 text-brand-800" : "bg-red-50 text-red-800";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>{status}</span>;
}
