import { Suspense } from "react";
import { JobBoard } from "@/components/JobBoard";
import { HeaderStats, HeaderStatsSkeleton } from "@/components/RefreshStatus";

export default function Home() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
          Tech jobs and internships in India
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600">
          Collected daily from public job APIs, deduplicated, and labelled by role and city with an LLM. Every
          listing links to the original posting.
        </p>
      </div>
      <Suspense fallback={<HeaderStatsSkeleton />}>
        <HeaderStats />
      </Suspense>
      <Suspense fallback={<p className="text-sm text-slate-500">Loading job search…</p>}>
        <JobBoard />
      </Suspense>
    </div>
  );
}
