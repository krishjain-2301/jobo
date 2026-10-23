export type Status = "new" | "portal" | "ready" | "no_email" | "drafted" | "approved" | "sent" | "applied" | "failed" | "skipped";
export type Level = "intern" | "entry" | "open" | "mid" | "senior";

export interface Profile {
  name: string;
  email: string;
  phone: string;
  linkedin: string;
  target_role: string;
  pitch: string;
  resume_path: string;
  provider: string;
  model: string;
  base_url: string;
  smtp_host: string;
  smtp_port: number;
  daily_limit: number;
  delay_min: number;
  delay_max: number;
  keywords: string;
  min_match: number;
  fresher_only: boolean;
}

export interface Task {
  id: string;
  kind: "discover" | "contacts" | "compose" | "send" | "webfind";
  label: string;
  state: "running" | "done" | "error" | "cancelled";
  done: number;
  total: number;
  message: string;
  error: string;
  result: Record<string, unknown>;
  started_at: string;
}

export interface AppState {
  profile: Profile;
  suggested_keywords: string;
  starter_lists: Record<string, { label: string; count: number }>;
  secrets: Record<string, boolean>;
  gmail_address: string;
  resume: { name: string | null; skills: string[] };
  counts: Partial<Record<Status, number>>;
  sent_total: number;
  sent_24h: number;
  allowance: number;
  checks: { resume: boolean; profile: boolean; gmail: boolean };
  providers: Record<string, { models: string[]; needs_base_url: boolean }>;
  boards: string[];
  countries: string[];
  tasks: Task[];
}

export interface Company {
  id: number;
  name: string;
  website: string | null;
  job_title: string | null;
  job_url: string | null;
  job_description: string | null;
  location: string | null;
  source: string | null;
  emails: string[];
  email: string | null;
  careers_url: string | null;
  status: Status;
  subject: string | null;
  body: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  match_score: number | null;
  match_level: Level | null;
  matched: string[];
  missing: string[];
}

export type AtsKind = "greenhouse" | "lever" | "ashby" | "workable" | "smartrecruiters" | "workday" | "recruitee" | "personio";

export interface DiscoveredBoard {
  ats: AtsKind;
  token: string;
  hits: number;
  samples: string[];
  url: string;
  known: boolean;
}

export interface Watch {
  id: number;
  name: string;
  ats: AtsKind;
  token: string;
  website: string | null;
  last_scanned: string | null;
  jobs_total: number | null;
  jobs_matched: number | null;
  error: string | null;
}

export interface JobResult {
  company: string;
  title: string;
  url: string;
  location: string;
  source: string;
  score: number;
  level: Level;
  matched: string[];
  missing: string[];
  passed: boolean;
  status: "added" | "updated" | "kept" | "other" | "hidden";
}

export interface DiscoverResult {
  found: number;
  passed: number;
  companies: number;
  added: number;
  updated: number;
  errors: Record<string, string>;
  jobs: JobResult[];
  providers?: Record<string, number>;
}

export interface SentRow {
  id: number;
  company_id: number;
  company: string;
  email: string;
  subject: string;
  sent_at: string;
}

export class ApiError extends Error {}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  const res = await fetch(`/api${path}`, init);
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail)) message = data.detail.map((d: { msg: string }) => d.msg).join(", ");
    } catch {
      /* not JSON */
    }
    throw new ApiError(message);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};
