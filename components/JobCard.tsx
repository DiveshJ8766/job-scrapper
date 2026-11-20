import Link from "next/link";
import { sourceLabel } from "@/lib/constants";
import { formatDate } from "@/lib/format";
import type { JobSummary } from "@/lib/types";
import { AdzunaAttribution } from "./AdzunaAttribution";
import { Badge } from "./Badge";

export function JobCard({ job }: { job: JobSummary }) {
  const classified = job.classificationStatus === "classified";
  const place = classified ? job.cities.join(" · ") : job.locationRaw || "Location not listed";
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-slate-900">
            <Link href={`/jobs/${job.id}`} className="hover:text-brand-700 hover:underline">
              {job.title}
            </Link>
          </h3>
          <p className="mt-0.5 text-sm text-slate-700">{job.company}</p>
          <p className="mt-1 text-sm text-slate-500">
            <span className="sr-only">Location: </span>
            {place}
          </p>
        </div>
        <a
          href={job.applicationUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex shrink-0 items-center justify-center rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          Apply<span className="sr-only"> to {job.title} at {job.company} (opens original posting)</span>
          <span aria-hidden className="ml-1">↗</span>
        </a>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {classified ? (
          <>
            {job.role && <Badge tone="brand">{job.role}</Badge>}
            {job.jobType && job.jobType !== "Unknown" && <Badge tone="green">{job.jobType}</Badge>}
            {job.experienceLevel && job.experienceLevel !== "Unknown" && <Badge>{job.experienceLevel}</Badge>}
          </>
        ) : (
          <Badge tone="amber">Classification pending</Badge>
        )}
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
        <span>
          {job.postedAt ? `Posted ${formatDate(job.postedAt)}` : `First seen ${formatDate(job.firstSeenAt)}`} · via {sourceLabel(job.sourceName)}
        </span>
        {job.sourceName === "adzuna" && <AdzunaAttribution />}
      </div>
    </article>
  );
}

export function JobCardSkeleton() {
  return (
    <div aria-hidden className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="h-4 w-2/3 rounded bg-slate-200" />
      <div className="mt-2 h-3 w-1/3 rounded bg-slate-100" />
      <div className="mt-2 h-3 w-1/4 rounded bg-slate-100" />
      <div className="mt-4 flex gap-2">
        <div className="h-5 w-24 rounded-full bg-slate-100" />
        <div className="h-5 w-16 rounded-full bg-slate-100" />
      </div>
    </div>
  );
}
