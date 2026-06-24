import type {
  ActiveSessions,
  Feed,
  Health,
  Job,
  JobAck,
  Metrics,
  ModelsResponse,
  PipelineStatus,
  RecentEvent,
  Report,
  ScenarioName,
  SimStatus,
  Variant,
} from "./types";

export const API_BASE: string =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ||
  "http://localhost:8000";

async function request<T>(
  path: string,
  init?: RequestInit & { timeoutMs?: number }
): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = init?.timeoutMs ?? 8000;
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...(init?.headers ?? {}),
      },
    });
    if (!res.ok) {
      throw new Error(`${init?.method ?? "GET"} ${path} -> ${res.status}`);
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

function qs(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== ""
  );
  if (entries.length === 0) return "";
  const usp = new URLSearchParams();
  for (const [k, v] of entries) usp.set(k, String(v));
  return `?${usp.toString()}`;
}

// ---- GET endpoints ----------------------------------------------------------

export const getHealth = () => request<Health>("/health");

export const getFeed = (opts: {
  user_id: number;
  k?: number;
  variant?: Variant;
  session_id?: string;
}) =>
  request<Feed>(
    `/feed${qs({
      user_id: opts.user_id,
      k: opts.k,
      variant: opts.variant,
      session_id: opts.session_id,
    })}`
  );

export const getMetrics = (windowMinutes = 30) =>
  request<Metrics>(`/metrics${qs({ window_minutes: windowMinutes })}`);

export const getModels = () => request<ModelsResponse>("/models");

export const getSimStatus = () => request<SimStatus>("/sim/status");

export const getPipelineStatus = () =>
  request<PipelineStatus>("/pipeline/status");

export const getRecentEvents = (limit = 40) =>
  request<RecentEvent[]>(`/events/recent${qs({ limit })}`);

export const getActiveSessions = () =>
  request<ActiveSessions>("/sessions/active");

export const getSampleUsers = (n = 8) =>
  request<number[]>(`/users/sample${qs({ n })}`);

export const getReport = () => request<Report>("/report");

export const getRecentJobs = () => request<Job[]>("/jobs/recent");

// ---- POST endpoints ---------------------------------------------------------

export const startSim = (rate?: number) =>
  request<SimStatus>("/sim/start", {
    method: "POST",
    body: JSON.stringify(rate !== undefined ? { rate } : {}),
  });

export const stopSim = () =>
  request<SimStatus>("/sim/stop", { method: "POST", body: JSON.stringify({}) });

export const setScenario = (scenario: ScenarioName, intensity: number) =>
  request<SimStatus>("/sim/scenario", {
    method: "POST",
    body: JSON.stringify({ scenario, intensity }),
  });

export const retrain = () =>
  request<JobAck>("/retrain", { method: "POST", body: JSON.stringify({}) });

export const reset = () =>
  request<JobAck>("/reset", { method: "POST", body: JSON.stringify({}) });
