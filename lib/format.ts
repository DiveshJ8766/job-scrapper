// Fixed time zone so server and client render identical strings (no hydration mismatch).
const TZ = "Asia/Kolkata";

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: TZ }).format(
    new Date(iso),
  );
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: TZ,
    timeZoneName: "short",
  }).format(new Date(iso));
}

export function formatUsd(n: number | null | undefined, digits = 4): string {
  if (n === null || n === undefined) return "—";
  return `$${n.toFixed(digits)}`;
}
