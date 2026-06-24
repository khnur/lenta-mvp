import { getPipelineStatus, getRecentJobs } from "../api";
import { usePolling } from "../hooks/usePolling";
import { Badge, Empty, Panel, fmtAgo, fmtMs, fmtTime } from "../ui";

const STAGE_ORDER = ["ingest", "feature_update", "retrain", "deploy"];

function statusTone(s: string): "green" | "amber" | "red" | "blue" | "slate" {
  const v = s.toLowerCase();
  if (["ok", "success", "done", "complete", "completed", "deployed", "active"].includes(v))
    return "green";
  if (["running", "in_progress", "started", "pending", "queued"].includes(v))
    return "blue";
  if (["warn", "warning", "stale", "skipped"].includes(v)) return "amber";
  if (["error", "failed", "fail"].includes(v)) return "red";
  return "slate";
}

function prettyStage(s: string): string {
  return s.replace(/_/g, " ");
}

export function PipelineStatus() {
  const pipeline = usePolling(getPipelineStatus, 2000);
  const jobs = usePolling(getRecentJobs, 2000);

  const stages = pipeline.data?.stages ?? [];
  const ordered = [...stages].sort(
    (a, b) =>
      (STAGE_ORDER.indexOf(a.stage) + 100) % 100 -
      ((STAGE_ORDER.indexOf(b.stage) + 100) % 100)
  );
  const runs = pipeline.data?.runs ?? [];

  return (
    <Panel
      title="Pipeline status"
      subtitle={
        pipeline.reconnecting || jobs.reconnecting ? (
          <span className="text-amber-400">reconnecting…</span>
        ) : (
          "ingest → features → retrain → deploy"
        )
      }
      right={
        pipeline.data?.active_model_version !== null &&
        pipeline.data?.active_model_version !== undefined ? (
          <Badge tone="green">model v{pipeline.data.active_model_version}</Badge>
        ) : (
          <Badge tone="slate">no model</Badge>
        )
      }
      className="xl:col-span-2"
    >
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Stages */}
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
            Stages
          </h3>
          {ordered.length === 0 ? (
            <Empty>No pipeline data</Empty>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {ordered.map((st) => (
                <div
                  key={st.stage}
                  className="rounded-lg border border-white/5 bg-bg-elevated p-3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium capitalize text-slate-100">
                      {prettyStage(st.stage)}
                    </span>
                    <Badge tone={statusTone(st.status)}>{st.status}</Badge>
                  </div>
                  <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
                    <span>{fmtAgo(st.last_run)}</span>
                    <span className="font-mono">{fmtMs(st.duration_ms)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent runs + jobs */}
        <div className="space-y-4">
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Recent runs
            </h3>
            <div className="scroll-thin max-h-40 space-y-1 overflow-y-auto pr-1">
              {runs.length === 0 ? (
                <Empty>No runs yet</Empty>
              ) : (
                runs.map((r, i) => (
                  <div
                    key={`${r.stage}-${r.last_run}-${i}`}
                    className="flex items-center gap-2 rounded-md border border-white/5 bg-bg-elevated px-2.5 py-1.5 text-xs"
                  >
                    <span className="h-2 w-2 shrink-0 rounded-full bg-sky-400" />
                    <span className="w-28 shrink-0 truncate capitalize text-slate-200">
                      {prettyStage(r.stage)}
                    </span>
                    <Badge tone={statusTone(r.status)}>{r.status}</Badge>
                    <span className="ml-auto shrink-0 font-mono text-[10px] text-slate-500">
                      {fmtMs(r.duration_ms)}
                    </span>
                    <span className="w-16 shrink-0 text-right text-[10px] text-slate-500">
                      {fmtAgo(r.last_run)}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>

          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Recent jobs
            </h3>
            <div className="scroll-thin max-h-40 space-y-1 overflow-y-auto pr-1">
              {(jobs.data ?? []).length === 0 ? (
                <Empty>No jobs yet</Empty>
              ) : (
                (jobs.data ?? []).map((j) => (
                  <div
                    key={j.id}
                    className="flex items-center gap-2 rounded-md border border-white/5 bg-bg-elevated px-2.5 py-1.5 text-xs"
                  >
                    <span className="font-mono text-[10px] text-slate-500">
                      #{j.id}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-slate-200">
                      {j.type}
                    </span>
                    <Badge tone={statusTone(j.status)}>{j.status}</Badge>
                    <span className="w-16 shrink-0 text-right text-[10px] text-slate-500">
                      {fmtTime(j.finished_at ?? j.created_at)}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </Panel>
  );
}
