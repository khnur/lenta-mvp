import { getHealth, getPipelineStatus, getReport, getSimStatus } from "../api";
import { usePolling } from "../hooks/usePolling";
import { useOnboarding } from "../onboarding/Onboarding";
import { Badge } from "../ui";

export function Header() {
  const health = usePolling(getHealth, 2000);
  const sim = usePolling(getSimStatus, 2000);
  const pipeline = usePolling(getPipelineStatus, 2000);
  const report = usePolling(getReport, 2000);
  const { start: startTour, seen } = useOnboarding();

  const modelVersion =
    health.data?.model_version ?? pipeline.data?.active_model_version ?? null;
  const totalEvents = pipeline.data?.total_events ?? 0;
  const running = sim.data?.running ?? false;

  const anyReconnecting =
    health.reconnecting ||
    sim.reconnecting ||
    pipeline.reconnecting ||
    report.reconnecting;

  return (
    <header className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-bold tracking-tight text-slate-50">
            Lenta
          </h1>
          <span className="text-sm text-slate-400">— live recommender</span>
          {anyReconnecting ? (
            <span className="flex items-center gap-1.5 text-xs text-amber-400">
              <span className="h-2 w-2 animate-pulse rounded-full bg-amber-400" />
              reconnecting…
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-xs text-emerald-400">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              live
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={startTour}
            title="Take a guided tour of the dashboard"
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition ${
              seen
                ? "border-white/10 bg-bg-elevated text-slate-300 hover:border-sky-400/50 hover:text-sky-200"
                : "border-sky-400/60 bg-sky-500/15 text-sky-200 hover:bg-sky-500/25"
            }`}
          >
            <span aria-hidden>✨</span> Tour
          </button>
          <div
            data-tour="tour-status"
            className="flex flex-wrap items-center gap-2"
          >
            <Badge tone={modelVersion !== null ? "green" : "slate"}>
              model {modelVersion !== null ? `v${modelVersion}` : "—"}
            </Badge>
            <Badge tone="blue">{totalEvents.toLocaleString()} events</Badge>
            <Badge tone={running ? "green" : "slate"}>
              sim {running ? "running" : "stopped"} · {sim.data?.rate ?? 0}/s ·{" "}
              {sim.data?.scenario ?? "—"}
            </Badge>
            {health.data ? (
              <Badge
                tone={
                  health.data.status === "ok" || health.data.model_ready
                    ? "green"
                    : "amber"
                }
              >
                db {health.data.db} · redis {health.data.redis}
              </Badge>
            ) : null}
          </div>
        </div>
      </div>

      {/* "What changed" banner from /report */}
      <div
        data-tour="tour-report"
        className="rounded-xl border border-sky-500/30 bg-gradient-to-r from-sky-500/15 to-violet-500/10 px-4 py-3"
      >
        <div className="flex items-center gap-3">
          <span className="shrink-0 text-[11px] font-semibold uppercase tracking-wider text-sky-300">
            What changed
          </span>
          <p className="min-w-0 flex-1 text-sm text-slate-100">
            {report.data?.text ?? "Waiting for the first report…"}
          </p>
          {report.data?.version !== null && report.data?.version !== undefined ? (
            <Badge tone="purple">v{report.data.version}</Badge>
          ) : null}
        </div>
        {report.data &&
        (report.data.delta_ndcg !== undefined ||
          report.data.delta_recall !== undefined ||
          (report.data.genre_movers && report.data.genre_movers.length > 0)) ? (
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
            {report.data.delta_ndcg !== undefined ? (
              <Delta label="Δ ndcg" value={report.data.delta_ndcg} />
            ) : null}
            {report.data.delta_recall !== undefined ? (
              <Delta label="Δ recall" value={report.data.delta_recall} />
            ) : null}
            {(report.data.genre_movers ?? []).slice(0, 5).map((g) => (
              <span key={g.genre} className="text-slate-300">
                {g.genre}{" "}
                <span className={g.delta >= 0 ? "text-emerald-400" : "text-red-400"}>
                  {g.delta >= 0 ? "+" : ""}
                  {g.delta.toFixed(2)}
                </span>
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </header>
  );
}

function Delta({ label, value }: { label: string; value: number }) {
  const positive = value >= 0;
  return (
    <span className="text-slate-400">
      {label}:{" "}
      <span className={positive ? "text-emerald-400" : "text-red-400"}>
        {positive ? "+" : ""}
        {value.toFixed(3)}
      </span>
    </span>
  );
}
