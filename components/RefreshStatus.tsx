import { connection } from "next/server";
import { formatDateTime } from "@/lib/format";
import { getStats } from "@/lib/queries";

export async function HeaderStats() {
  await connection();
  let stats;
  try {
    stats = await getStats();
  } catch (err) {
    console.error("[page] stats unavailable", err);
    return <p className="text-sm text-slate-500">Live stats are unavailable right now.</p>;
  }
  const run = stats.lastSuccessfulRun;
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Stat label="Open jobs" value={stats.activeJobs.toLocaleString("en-IN")} />
      <Stat label="Companies" value={stats.companies.toLocaleString("en-IN")} />
      <Stat label="Classified by AI" value={stats.classification.classified.toLocaleString("en-IN")} />
      <Stat label="Last refreshed" value={run ? formatDateTime(run.completedAt) : "Not yet"} small />
    </dl>
  );
}

function Stat({ label, value, small }: { label: string; value: string; small?: boolean }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className={`mt-1 font-semibold text-slate-900 ${small ? "text-sm" : "text-xl"}`}>{value}</dd>
    </div>
  );
}

export function HeaderStatsSkeleton() {
  return (
    <div aria-hidden className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {Array.from({ length: 4 }, (_, i) => (
        <div key={i} className="h-[68px] rounded-lg border border-slate-200 bg-white" />
      ))}
    </div>
  );
}
