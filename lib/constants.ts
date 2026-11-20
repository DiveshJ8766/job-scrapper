// Must match pipeline/classify/schema.py and the CHECK constraints in db/migrations.
export const ROLES = [
  "Frontend Developer",
  "Backend Developer",
  "Full Stack Developer",
  "Software Engineer",
  "Data Analyst",
  "Data Scientist",
  "Machine Learning Engineer",
  "AI Engineer",
  "DevOps Engineer",
  "QA Engineer",
  "UI UX Designer",
  "Product Manager",
  "Other",
  "Unknown",
] as const;

export const JOB_TYPES = ["Full-time", "Part-time", "Internship", "Contract", "Temporary", "Unknown"] as const;

export const EXPERIENCE_LEVELS = ["Internship", "Fresher", "Junior", "Mid", "Senior", "Unknown"] as const;

export const AGGREGATOR_SOURCES = new Set(["adzuna"]);

export function sourceLabel(sourceName: string): string {
  if (sourceName === "adzuna") return "Adzuna";
  const [ats] = sourceName.split(":");
  return ats ? ats.charAt(0).toUpperCase() + ats.slice(1) : sourceName;
}

export const PAGE_SIZE_DEFAULT = 20;
export const PAGE_SIZE_MAX = 50;
