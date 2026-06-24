// ----------------------------------------------------------------------------
// API response types — mirrors the live API contract for the Lenta recommender.
// ----------------------------------------------------------------------------

export type Variant = "treatment" | "control";

export interface Health {
  status: string;
  db: boolean;
  redis: boolean;
  model_ready: boolean;
  model_version: number | null;
}

// --- Feed --------------------------------------------------------------------

export interface FeedItem {
  id: number;
  title: string;
  creator_id: number;
  genres: string[];
  tags: string[];
  duration_seconds: number;
  upload_time: string;
  score: number;
  stage: string;
}

export interface Funnel {
  catalog: number;
  candidates: number;
  ranked: number;
  feed: number;
  retrieval: string;
  model_version: number | null;
  cold_start: boolean;
  latency_ms: number;
}

export interface Feed {
  user_id: number;
  variant: Variant;
  k: number;
  items: FeedItem[];
  funnel: Funnel;
}

// --- Metrics -----------------------------------------------------------------

export interface VariantMetrics {
  variant: string;
  impressions: number;
  clicks: number;
  plays: number;
  ctr: number;
  avg_watch_seconds: number;
  avg_watch_fraction: number;
  avg_session_length: number;
}

export interface MetricsLift {
  ctr: number;
  avg_watch_seconds: number;
  avg_watch_fraction: number;
  avg_session_length: number;
}

export interface Metrics {
  window_minutes: number;
  overall: VariantMetrics;
  per_variant: VariantMetrics[];
  lift: MetricsLift;
}

// --- Models ------------------------------------------------------------------

export interface ModelMetrics {
  recall_at_k: number;
  ndcg_at_k: number;
  coverage: number;
  diversity: number;
  k: number;
  n_users: number;
  train_events: number;
}

export interface ModelVersion {
  id: number;
  version: number;
  created_at: string;
  algo: string;
  is_active: boolean;
  artifact_bytes: number;
  train_rows: number;
  notes: string;
  metrics: ModelMetrics;
}

export interface ModelsResponse {
  active_version: number | null;
  versions: ModelVersion[];
}

// --- Simulation --------------------------------------------------------------

export type ScenarioName =
  | "genre_shift"
  | "new_content_surge"
  | "cold_start_wave"
  | "baseline";

export interface SimStatus {
  running: boolean;
  rate: number;
  scenario: string;
  emitted: number;
  updated_at: string | null;
}

// --- Pipeline ----------------------------------------------------------------

export interface PipelineStage {
  stage: string;
  status: string;
  last_run: string | null;
  duration_ms: number | null;
  detail: Record<string, unknown> | null;
}

export interface PipelineStatus {
  stages: PipelineStage[];
  active_model_version: number | null;
  total_events: number;
  runs: PipelineStage[];
}

// --- Events / sessions / users ----------------------------------------------

export type EventType = "impression" | "click" | "play";

export interface RecentEvent {
  id: number;
  user_id: number;
  video_id: number;
  title: string;
  event_type: string;
  variant: string;
  watch_fraction: number;
  ts: string;
}

export interface ActiveSession {
  session_id: string;
  user_id: number;
  last_genre: string;
  len: number;
}

export interface ActiveSessions {
  active_count: number;
  sessions: ActiveSession[];
}

// --- Report ------------------------------------------------------------------

export interface GenreMover {
  genre: string;
  delta: number;
}

export interface Report {
  text: string;
  version: number | null;
  prev_version?: number;
  delta_ndcg?: number;
  delta_recall?: number;
  genre_movers?: GenreMover[];
}

// --- Jobs --------------------------------------------------------------------

export interface Job {
  id: number | string;
  type: string;
  status: string;
  created_at: string;
  finished_at: string | null;
  result: unknown;
}

// --- Mutating actions --------------------------------------------------------

export interface JobAck {
  ok: boolean;
  job_id: number | string;
  status: string;
}
