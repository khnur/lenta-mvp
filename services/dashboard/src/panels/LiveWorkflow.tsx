import { useCallback, useEffect, useMemo, useState } from "react";
import { getActiveSessions, getFeed, getRecentEvents, getSampleUsers } from "../api";
import { usePolling } from "../hooks/usePolling";
import type { Funnel } from "../types";
import { Badge, Empty, Panel, fmtAgo, fmtFloat, fmtMs } from "../ui";

const STAGES: Array<{ key: keyof Pick<Funnel, "catalog" | "candidates" | "ranked" | "feed">; label: string; color: string }> = [
  { key: "catalog", label: "Catalog", color: "bg-slate-500" },
  { key: "candidates", label: "Candidates", color: "bg-sky-500" },
  { key: "ranked", label: "Ranked", color: "bg-violet-500" },
  { key: "feed", label: "Feed", color: "bg-emerald-500" },
];

function eventTone(t: string): "green" | "amber" | "blue" | "slate" {
  if (t === "play") return "green";
  if (t === "click") return "amber";
  if (t === "impression") return "blue";
  return "slate";
}

function FunnelBar({ funnel }: { funnel: Funnel }) {
  const max = Math.max(funnel.catalog, 1);
  return (
    <div className="space-y-2">
      {STAGES.map((s) => {
        const value = funnel[s.key];
        const pct = Math.max((value / max) * 100, value > 0 ? 2 : 0);
        return (
          <div key={s.key} className="flex items-center gap-2">
            <div className="w-20 shrink-0 text-xs text-slate-400">{s.label}</div>
            <div className="relative h-6 flex-1 overflow-hidden rounded bg-bg-elevated">
              <div
                className={`h-full ${s.color} transition-all duration-500`}
                style={{ width: `${pct}%` }}
              />
              <div className="absolute inset-0 flex items-center px-2 text-xs font-medium text-white/90">
                {value.toLocaleString()}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function LiveWorkflow() {
  const [users, setUsers] = useState<number[]>([]);
  const [selectedUser, setSelectedUser] = useState<number | null>(null);

  // Load sample users once (refresh occasionally so the dropdown stays valid).
  const usersPoll = usePolling(() => getSampleUsers(8), 30000);
  useEffect(() => {
    if (usersPoll.data && usersPoll.data.length > 0) {
      setUsers(usersPoll.data);
      setSelectedUser((cur) =>
        cur !== null && usersPoll.data!.includes(cur) ? cur : usersPoll.data![0]
      );
    }
  }, [usersPoll.data]);

  const feedFetcher = useCallback(() => {
    const uid = selectedUser ?? 1;
    return getFeed({ user_id: uid, k: 10, variant: "treatment" });
  }, [selectedUser]);

  const feed = usePolling(feedFetcher, 2000, selectedUser !== null);
  const events = usePolling(() => getRecentEvents(40), 2000);
  const sessions = usePolling(getActiveSessions, 2000);

  const reconnecting =
    feed.reconnecting || events.reconnecting || sessions.reconnecting;

  const funnel = feed.data?.funnel;
  const items = feed.data?.items ?? [];

  const subtitle = useMemo(
    () =>
      reconnecting ? (
        <span className="text-amber-400">reconnecting…</span>
      ) : (
        "feed re-fetched every 2s"
      ),
    [reconnecting]
  );

  return (
    <Panel
      title="Live workflow"
      subtitle={subtitle}
      tourId="tour-workflow"
      className="xl:col-span-2"
      right={
        <select
          value={selectedUser ?? ""}
          onChange={(e) => setSelectedUser(Number(e.target.value))}
          className="rounded-md border border-white/10 bg-bg-elevated px-2 py-1 text-xs text-slate-200 focus:border-accent focus:outline-none"
        >
          {users.length === 0 ? <option value="">loading…</option> : null}
          {users.map((u) => (
            <option key={u} value={u}>
              user {u}
            </option>
          ))}
        </select>
      }
    >
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Funnel + feed */}
        <div className="space-y-4">
          <div>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Funnel
              </h3>
              {funnel ? (
                <div className="flex items-center gap-2">
                  <Badge tone="slate">{funnel.retrieval}</Badge>
                  {funnel.cold_start ? (
                    <Badge tone="amber">cold start</Badge>
                  ) : null}
                  <Badge tone="blue">{fmtMs(funnel.latency_ms)}</Badge>
                </div>
              ) : null}
            </div>
            {funnel ? <FunnelBar funnel={funnel} /> : <Empty>No feed yet</Empty>}
          </div>

          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Current feed{selectedUser !== null ? ` · user ${selectedUser}` : ""}
            </h3>
            <div className="scroll-thin max-h-72 space-y-1.5 overflow-y-auto pr-1">
              {items.length === 0 ? (
                <Empty>No items</Empty>
              ) : (
                items.map((it, idx) => (
                  <div
                    key={`${it.id}-${idx}`}
                    className="flex items-center gap-2 rounded-lg border border-white/5 bg-bg-elevated px-2.5 py-1.5"
                  >
                    <span className="w-5 shrink-0 text-center text-xs font-mono text-slate-500">
                      {idx + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm text-slate-100">
                        {it.title}
                      </div>
                      <div className="truncate text-[11px] text-slate-400">
                        {it.genres.slice(0, 3).join(", ") || "—"}
                      </div>
                    </div>
                    <Badge tone="purple">{it.stage}</Badge>
                    <span className="w-12 shrink-0 text-right font-mono text-xs text-accent">
                      {fmtFloat(it.score, 2)}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Event ticker + sessions */}
        <div className="space-y-4">
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Event ticker
            </h3>
            <div className="scroll-thin max-h-72 space-y-1 overflow-y-auto pr-1">
              {(events.data ?? []).length === 0 ? (
                <Empty>No events</Empty>
              ) : (
                (events.data ?? []).map((ev) => (
                  <div
                    key={ev.id}
                    className="flex items-center gap-2 rounded-md border border-white/5 bg-bg-elevated px-2.5 py-1.5 text-xs"
                  >
                    <Badge tone={eventTone(ev.event_type)}>{ev.event_type}</Badge>
                    <span className="min-w-0 flex-1 truncate text-slate-200">
                      {ev.title}
                    </span>
                    <span className="shrink-0 font-mono text-[10px] text-slate-500">
                      u{ev.user_id} · {ev.variant}
                    </span>
                    <span className="w-14 shrink-0 text-right text-[10px] text-slate-500">
                      {fmtAgo(ev.ts)}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>

          <div>
            <h3 className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-slate-400">
              <span>Active sessions</span>
              <Badge tone="green">{sessions.data?.active_count ?? 0}</Badge>
            </h3>
            <div className="scroll-thin max-h-44 space-y-1 overflow-y-auto pr-1">
              {(sessions.data?.sessions ?? []).length === 0 ? (
                <Empty>No active sessions</Empty>
              ) : (
                (sessions.data?.sessions ?? []).map((s) => (
                  <div
                    key={s.session_id}
                    className="flex items-center gap-2 rounded-md border border-white/5 bg-bg-elevated px-2.5 py-1.5 text-xs"
                  >
                    <span className="font-mono text-[10px] text-slate-500">
                      u{s.user_id}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-slate-300">
                      {s.last_genre || "—"}
                    </span>
                    <Badge tone="slate">{s.len} ev</Badge>
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
