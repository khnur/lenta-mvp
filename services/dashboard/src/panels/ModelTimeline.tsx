import { useMemo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getModels } from "../api";
import { usePolling } from "../hooks/usePolling";
import { Badge, Empty, Panel } from "../ui";

const METRIC_LINES: Array<{ key: string; name: string; color: string }> = [
  { key: "recall_at_k", name: "recall@k", color: "#38bdf8" },
  { key: "ndcg_at_k", name: "ndcg@k", color: "#34d399" },
  { key: "coverage", name: "coverage", color: "#fbbf24" },
  { key: "diversity", name: "diversity", color: "#a78bfa" },
];

interface ChartRow {
  version: string;
  recall_at_k: number;
  ndcg_at_k: number;
  coverage: number;
  diversity: number;
}

export function ModelTimeline() {
  const models = usePolling(getModels, 2000);

  const rows: ChartRow[] = useMemo(() => {
    const versions = models.data?.versions ?? [];
    // API returns newest-first; reverse so x-axis goes oldest -> newest.
    return [...versions].reverse().map((v) => ({
      version: `v${v.version}`,
      recall_at_k: v.metrics.recall_at_k,
      ndcg_at_k: v.metrics.ndcg_at_k,
      coverage: v.metrics.coverage,
      diversity: v.metrics.diversity,
    }));
  }, [models.data]);

  const active = models.data?.active_version ?? null;

  return (
    <Panel
      title="Model timeline"
      tourId="tour-timeline"
      subtitle={
        models.reconnecting ? (
          <span className="text-amber-400">reconnecting…</span>
        ) : (
          "offline metrics per model version"
        )
      }
      right={
        active !== null ? (
          <Badge tone="green">active v{active}</Badge>
        ) : (
          <Badge tone="slate">no active model</Badge>
        )
      }
    >
      {rows.length === 0 ? (
        <Empty>No model versions yet — train one from the cockpit</Empty>
      ) : (
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: -8 }}>
              <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
              <XAxis
                dataKey="version"
                tick={{ fill: "#94a3b8", fontSize: 12 }}
                stroke="#334155"
              />
              <YAxis
                domain={[0, 1]}
                tick={{ fill: "#94a3b8", fontSize: 12 }}
                stroke="#334155"
                width={44}
              />
              <Tooltip
                contentStyle={{
                  background: "#1a2230",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelStyle={{ color: "#e2e8f0" }}
                formatter={(value: number | string) =>
                  typeof value === "number" ? value.toFixed(3) : value
                }
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {METRIC_LINES.map((m) => (
                <Line
                  key={m.key}
                  type="monotone"
                  dataKey={m.key}
                  name={m.name}
                  stroke={m.color}
                  strokeWidth={2}
                  dot={{ r: 2 }}
                  activeDot={{ r: 4 }}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  );
}
