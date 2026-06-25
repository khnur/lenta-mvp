import { useState } from "react";
import {
  getSimStatus,
  reset,
  retrain,
  setScenario,
  startSim,
  stopSim,
} from "../api";
import { usePolling } from "../hooks/usePolling";
import type { ScenarioName, SimStatus } from "../types";
import { Badge, Panel, fmtAgo } from "../ui";

const SCENARIOS: Array<{ name: ScenarioName; label: string; desc: string }> = [
  { name: "baseline", label: "Baseline", desc: "steady traffic" },
  { name: "genre_shift", label: "Genre shift", desc: "tastes move" },
  { name: "new_content_surge", label: "Content surge", desc: "fresh uploads" },
  { name: "cold_start_wave", label: "Cold start wave", desc: "new users" },
];

type Busy = string | null;

export function ScenarioControls({
  onStatusChange,
}: {
  onStatusChange?: (s: SimStatus) => void;
}) {
  const status = usePolling(getSimStatus, 2000);
  const [rate, setRate] = useState<number>(20);
  const [intensity, setIntensity] = useState<number>(0.6);
  const [busy, setBusy] = useState<Busy>(null);
  const [lastAction, setLastAction] = useState<string | null>(null);

  const live = status.data;

  async function run(label: string, fn: () => Promise<SimStatus | unknown>) {
    setBusy(label);
    try {
      const result = await fn();
      setLastAction(label);
      if (result && typeof result === "object" && "running" in result) {
        onStatusChange?.(result as SimStatus);
      }
      // Pull fresh status immediately so the pill updates without waiting.
      status.refresh();
    } catch {
      setLastAction(`${label} failed`);
    } finally {
      setBusy(null);
    }
  }

  function confirmReset() {
    if (
      window.confirm(
        "Reset will wipe events, sessions, models and metrics. Continue?"
      )
    ) {
      void run("reset", reset);
    }
  }

  const btn =
    "rounded-md px-3 py-1.5 text-xs font-medium transition disabled:opacity-40 disabled:cursor-not-allowed";

  return (
    <Panel
      title="Scenario controls"
      subtitle="the demo cockpit"
      tourId="tour-scenarios"
      right={
        live ? (
          <Badge tone={live.running ? "green" : "slate"}>
            {live.running ? "running" : "stopped"} · {live.rate}/s
          </Badge>
        ) : (
          <Badge tone="slate">sim status?</Badge>
        )
      }
    >
      <div className="space-y-4">
        {/* Sim status */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="rounded-lg border border-white/5 bg-bg-elevated px-3 py-2">
            <div className="text-[10px] uppercase text-slate-400">State</div>
            <div className={`text-sm font-semibold ${live?.running ? "text-accent-green" : "text-slate-300"}`}>
              {live?.running ? "running" : "stopped"}
            </div>
          </div>
          <div className="rounded-lg border border-white/5 bg-bg-elevated px-3 py-2">
            <div className="text-[10px] uppercase text-slate-400">Scenario</div>
            <div className="truncate text-sm font-semibold text-slate-100">
              {live?.scenario ?? "—"}
            </div>
          </div>
          <div className="rounded-lg border border-white/5 bg-bg-elevated px-3 py-2">
            <div className="text-[10px] uppercase text-slate-400">Emitted</div>
            <div className="text-sm font-semibold text-slate-100">
              {(live?.emitted ?? 0).toLocaleString()}
            </div>
          </div>
          <div className="rounded-lg border border-white/5 bg-bg-elevated px-3 py-2">
            <div className="text-[10px] uppercase text-slate-400">Updated</div>
            <div className="text-sm font-semibold text-slate-100">
              {fmtAgo(live?.updated_at)}
            </div>
          </div>
        </div>

        {/* Sim start/stop */}
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs text-slate-400">rate</label>
          <input
            type="number"
            min={1}
            max={500}
            value={rate}
            onChange={(e) => setRate(Math.max(1, Number(e.target.value) || 1))}
            className="w-20 rounded-md border border-white/10 bg-bg-elevated px-2 py-1 text-xs text-slate-200 focus:border-accent focus:outline-none"
          />
          <span className="text-xs text-slate-500">ev/s</span>
          <button
            disabled={busy !== null}
            onClick={() => void run("start", () => startSim(rate))}
            className={`${btn} bg-emerald-600 text-white hover:bg-emerald-500`}
          >
            ▶ Start sim
          </button>
          <button
            disabled={busy !== null}
            onClick={() => void run("stop", stopSim)}
            className={`${btn} bg-slate-700 text-slate-100 hover:bg-slate-600`}
          >
            ■ Stop
          </button>
        </div>

        {/* Scenarios + intensity */}
        <div>
          <div className="mb-2 flex items-center gap-2">
            <span className="text-xs text-slate-400">intensity</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={intensity}
              onChange={(e) => setIntensity(Number(e.target.value))}
              className="h-1.5 flex-1 cursor-pointer accent-sky-400"
            />
            <span className="w-10 text-right font-mono text-xs text-accent">
              {intensity.toFixed(2)}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {SCENARIOS.map((s) => {
              const activeScenario = live?.scenario === s.name;
              return (
                <button
                  key={s.name}
                  disabled={busy !== null}
                  onClick={() =>
                    void run(`scenario:${s.name}`, () =>
                      setScenario(s.name, intensity)
                    )
                  }
                  className={`${btn} flex flex-col items-start gap-0.5 border text-left ${
                    activeScenario
                      ? "border-sky-400 bg-sky-500/15 text-sky-200"
                      : "border-white/10 bg-bg-elevated text-slate-200 hover:border-sky-400/50"
                  }`}
                >
                  <span>{s.label}</span>
                  <span className="text-[10px] font-normal text-slate-400">
                    {s.desc}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Highlighted demo flow */}
        <div
          data-tour="tour-demo"
          className="rounded-lg border border-violet-500/30 bg-violet-500/10 p-3"
        >
          <div className="mb-2 flex items-center gap-2">
            <Badge tone="purple">Run the demo</Badge>
            <span className="text-xs text-slate-300">
              genre shift → retrain to watch metrics recover
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              disabled={busy !== null}
              onClick={() =>
                void run("scenario:genre_shift", () =>
                  setScenario("genre_shift", intensity)
                )
              }
              className={`${btn} bg-violet-600 text-white hover:bg-violet-500`}
            >
              1 · Trigger genre shift
            </button>
            <span className="text-violet-300">→</span>
            <button
              disabled={busy !== null}
              onClick={() => void run("retrain", retrain)}
              className={`${btn} bg-violet-600 text-white hover:bg-violet-500`}
            >
              2 · Retrain model
            </button>
          </div>
        </div>

        {/* Danger zone */}
        <div className="flex items-center justify-between gap-2 border-t border-white/5 pt-3">
          <div className="text-xs text-slate-500">
            {busy ? (
              <span className="text-amber-400">{busy}…</span>
            ) : lastAction ? (
              <span>last: {lastAction}</span>
            ) : (
              <span>ready</span>
            )}
          </div>
          <div className="flex gap-2">
            <button
              disabled={busy !== null}
              onClick={() => void run("retrain", retrain)}
              className={`${btn} bg-sky-700 text-white hover:bg-sky-600`}
            >
              Retrain
            </button>
            <button
              disabled={busy !== null}
              onClick={confirmReset}
              className={`${btn} bg-red-700 text-white hover:bg-red-600`}
            >
              Reset
            </button>
          </div>
        </div>
      </div>
    </Panel>
  );
}
