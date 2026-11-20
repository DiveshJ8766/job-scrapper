// API response shapes shared by route handlers and client components.

export interface JobSummary {
  id: number;
  title: string;
  company: string;
  city: string | null;
  cities: string[];
  isRemote: boolean;
  role: string | null;
  jobType: string | null;
  experienceLevel: string | null;
  locationRaw: string | null;
  applicationUrl: string;
  sourceName: string;
  postedAt: string | null;
  firstSeenAt: string;
  classificationStatus: string;
  isActive: boolean;
}

export interface JobDetail extends JobSummary {
  description: string | null;
  employmentTypeRaw: string | null;
  classificationModel: string | null;
  classifiedAt: string | null;
  sources: { sourceName: string; sourceUrl: string; firstSeenAt: string; lastSeenAt: string }[];
}

export interface JobsResponse {
  data: JobSummary[];
  pagination: { page: number; pageSize: number; total: number; totalPages: number };
}

export interface FacetValue {
  value: string;
  count: number;
}

export interface FiltersResponse {
  roles: FacetValue[];
  cities: FacetValue[];
  jobTypes: FacetValue[];
  experienceLevels: FacetValue[];
}

export interface RunSummary {
  id: number;
  status: string;
  trigger: string;
  startedAt: string;
  completedAt: string | null;
  jobsFetched: number;
  jobsInserted: number;
  duplicatesRemoved: number;
  jobsClassified: number;
}

export interface StatsResponse {
  activeJobs: number;
  companies: number;
  classification: { classified: number; pending: number; failed: number };
  sources: FacetValue[];
  lastSuccessfulRun: RunSummary | null;
  lastRun: RunSummary | null;
  llm: {
    requests: number;
    inputTokens: number;
    outputTokens: number;
    totalCostUsd: number;
    jobsClassified: number;
    avgCostPerJobUsd: number | null;
    costPer1000JobsUsd: number | null;
    models: string[];
  };
}

export interface ApiError {
  error: string;
  details?: unknown;
}
