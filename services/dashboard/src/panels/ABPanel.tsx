import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getMetrics } from "../api";
import { usePolling } from "../hooks/usePolling";
import type { VariantMetrics } from "../types";
import { Empty, Panel, StatCard, fmtPct, fmtSeconds } from "../ui";

const TREATMENT_COLOR = "#34d399";
const CONTROL_COLOR = "#64748b";

function pickVariant(
  list: VariantMetrics[],
  name: string
): VariantMetrics | undefined {
  return list.find((v) => v.variant === name);
}

function LiftReadout({ label, value }: { label: string; value: number | undefined }) {
  const positive = (value ?? 0) >= 0;
  const tone = value === undefined ? "default" : positive ? "green" : "red";
  const sign = value === undefined ? "" : positive ? "+" : "";
  return (
    <StatCard
      label={label}
      accent={tone as "green" | "red" | "default"}
      value={value === undefined ? "—" : `${sign}${(value * 100).toFixed(1)}%`}
    />
  );
}

export function ABPanel() {
  const metrics = usePolling(() => getMetrics(30), 2000);

  const perVariant = metrics.data?.per_variant ?? [];
  const treatment = pickVariant(perVariant, "treatment");
  const control = pickVariant(perVariant, "control");
  const lift = metrics.data?.lift;

  const chartData = useMemo(
    () => [
      {
        metric: "CTR",
        treatment: treatment?.ctr ?? 0,
        control: control?.ctr ?? 0,
      },
      {
        metric: "Watch s",
        treatment: treatment?.avg_watch_seconds ?? 0,
        control: control?.avg_watch_seconds ?? 0,
      },
      {
        metric: "Session len",
        treatment: treatment?.avg_session_length ?? 0,
        control: control?.avg_session_length ?? 0,
      },
    ],
    [treatment, control]
  );

  const hasAny = treatment !== undefined || control !== undefined;

  return (
    <Panel
      title="A/B test"
      subtitle={
        metrics.reconnecting ? (
          <span className="text-amber-400">reconnecting…</span>
        ) : (
          `last ${metrics.data?.window_minutes ?? 30} min`
        )
      }
      right={
        <div className="flex items-center gap-2 text-[11px]">
          <span className="flex items-center gap-1 text-emerald-300">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            treatment = recommender
          </span>
          <span className="flex items-center gap-1 text-slate-400">
            <span className="h-2 w-2 rounded-full bg-slate-500" />
            control = popularity
          </span>
        </div>
      }
    >
      {!hasAny ? (
        <Empty>No A/B traffic yet — start the simulation</Empty>
      ) : (
        <div className="space-y-4">
          {/* Lift readouts */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <LiftReadout label="CTR lift" value={lift?.ctr} />
            <LiftReadout label="Watch lift" value={lift?.avg_watch_seconds} />
            <LiftReadout label="Watch frac lift" value={lift?.avg_watch_fraction} />
            <LiftReadout label="Session lift" value={lift?.avg_session_length} />
          </div>

          {/* Stat cards: raw values */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <StatCard
              label="CTR (T / C)"
              value={
                <span>
                  <span className="text-accent-green">{fmtPct(treatment?.ctr)}</span>
                  <span className="text-slate-500"> / </span>
                  <span className="text-slate-300">{fmtPct(control?.ctr)}</span>
                </span>
              }
            />
            <StatCard
              label="Avg watch (T / C)"
              value={
                <span>
                  <span className="text-accent-green">
                    {fmtSeconds(treatment?.avg_watch_seconds)}
                  </span>
                  <span className="text-slate-500"> / </span>
                  <span className="text-slate-300">
                    {fmtSeconds(control?.avg_watch_seconds)}
                  </span>
                </span>
              }
            />
            <StatCard
              label="Session len (T / C)"
              value={
                <span>
                  <span className="text-accent-green">
                    {(treatment?.avg_session_length ?? 0).toFixed(1)}
                  </span>
                  <span className="text-slate-500"> / </span>
                  <span className="text-slate-300">
                    {(control?.avg_session_length ?? 0).toFixed(1)}
                  </span>
                </span>
              }
            />
          </div>

          {/* Grouped bars */}
          <div className="h-48 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 4, left: -12 }}>
                <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
                <XAxis
                  dataKey="metric"
                  tick={{ fill: "#94a3b8", fontSize: 12 }}
                  stroke="#334155"
                />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 12 }} stroke="#334155" width={44} />
                <Tooltip
                  cursor={{ fill: "rgba(255,255,255,0.04)" }}
                  contentStyle={{
                    background: "#1a2230",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  formatter={(value: number | string) =>
                    typeof value === "number" ? value.toFixed(3) : value
                  }
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="treatment" name="treatment" fill={TREATMENT_COLOR} radius={[3, 3, 0, 0]}>
                  {chartData.map((_, i) => (
                    <Cell key={i} fill={TREATMENT_COLOR} />
                  ))}
                </Bar>
                <Bar dataKey="control" name="control" fill={CONTROL_COLOR} radius={[3, 3, 0, 0]}>
                  {chartData.map((_, i) => (
                    <Cell key={i} fill={CONTROL_COLOR} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </Panel>
  );
}
