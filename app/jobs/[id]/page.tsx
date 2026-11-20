import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { AdzunaAttribution } from "@/components/AdzunaAttribution";
import { Badge } from "@/components/Badge";
import { sourceLabel } from "@/lib/constants";
import { formatDate, formatDateTime } from "@/lib/format";
import { getJob } from "@/lib/queries";
import { jobIdSchema } from "@/lib/validation";

export default function JobPage({ params }: PageProps<"/jobs/[id]">) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <Link href="/" className="text-sm font-medium text-brand-700 hover:underline">
        ← Back to all jobs
      </Link>
      <Suspense fallback={<p className="mt-6 text-sm text-slate-500">Loading job…</p>}>
        <JobDetail params={params} />
      </Suspense>
    </div>
  );
}

async function JobDetail({ params }: { params: PageProps<"/jobs/[id]">["params"] }) {
  const { id } = await params;
  const parsed = jobIdSchema.safeParse(id);
  if (!parsed.success) notFound();
  const job = await getJob(parsed.data);
  if (!job) notFound();
  const classified = job.classificationStatus === "classified";

  return (
    <article className="mt-4 rounded-lg border border-slate-200 bg-white p-5 sm:p-7">
      {!job.isActive && (
        <p className="mb-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
          This posting was not seen in recent refreshes and may be closed.
        </p>
      )}
      <h1 className="text-2xl font-semibold text-slate-900">{job.title}</h1>
      <p className="mt-1 text-slate-700">{job.company}</p>
      <div className="mt-4 flex flex-wrap gap-2">
        {classified ? (
          <>
            {job.role && <Badge tone="brand">{job.role}</Badge>}
            {job.jobType && <Badge tone="green">{job.jobType}</Badge>}
            {job.experienceLevel && <Badge>{job.experienceLevel}</Badge>}
            {job.cities.map((c) => (
              <Badge key={c}>{c}</Badge>
            ))}
          </>
        ) : (
          <Badge tone="amber">Classification pending</Badge>
        )}
      </div>

      <dl className="mt-6 grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-slate-500">Location (as listed)</dt>
          <dd className="text-slate-900">{job.locationRaw || "Not listed"}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Employment type (as listed)</dt>
          <dd className="text-slate-900">{job.employmentTypeRaw || "Not listed"}</dd>
        </div>
        <div>
          <dt className="text-slate-500">{job.postedAt ? "Posted" : "First seen"}</dt>
          <dd className="text-slate-900">{formatDate(job.postedAt ?? job.firstSeenAt)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Source</dt>
          <dd className="text-slate-900">{sourceLabel(job.sourceName)}</dd>
        </div>
      </dl>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <a
          href={job.applicationUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          Apply on original posting <span aria-hidden className="ml-1">↗</span>
        </a>
        {job.sourceName === "adzuna" && <AdzunaAttribution />}
      </div>

      <section className="mt-8">
        <h2 className="text-sm font-semibold text-slate-900">Description</h2>
        {job.sourceName === "adzuna" && (
          <p className="mt-1 text-xs text-slate-500">Adzuna provides a short excerpt. Open the posting for full details.</p>
        )}
        <div className="mt-2 whitespace-pre-line text-sm leading-6 text-slate-700">
          {job.description || "No description provided by the source."}
        </div>
      </section>

      <section className="mt-8 border-t border-slate-200 pt-5 text-xs text-slate-500">
        <h2 className="font-semibold text-slate-700">Data provenance</h2>
        <ul className="mt-2 space-y-1">
          {job.sources.map((s) => (
            <li key={s.sourceName + s.sourceUrl}>
              {sourceLabel(s.sourceName)} ({s.sourceName}) · first seen {formatDate(s.firstSeenAt)} ·{" "}
              <a href={s.sourceUrl} target="_blank" rel="noopener noreferrer" className="underline">
                original link
              </a>
            </li>
          ))}
        </ul>
        {classified && (
          <p className="mt-2">
            Classified by {job.classificationModel} on {formatDateTime(job.classifiedAt)}.
          </p>
        )}
      </section>
    </article>
  );
}
