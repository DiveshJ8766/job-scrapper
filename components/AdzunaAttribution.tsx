// Adzuna API terms require a visible "Jobs by Adzuna" label (min 116x23px) on every
// displayed Adzuna listing, with "Jobs" linking to the local Adzuna site.
export function AdzunaAttribution() {
  return (
    <span className="inline-flex h-[23px] min-w-[116px] items-center justify-center rounded border border-slate-200 bg-white px-2 text-xs text-slate-600">
      <a href="https://www.adzuna.in" target="_blank" rel="noopener noreferrer" className="underline-offset-2 hover:underline">
        Jobs
      </a>
      &nbsp;by&nbsp;
      <a href="https://www.adzuna.in" target="_blank" rel="noopener noreferrer" className="font-semibold hover:underline">
        Adzuna
      </a>
    </span>
  );
}
