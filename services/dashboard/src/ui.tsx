import type { ReactNode } from "react";

// ---- Formatters -------------------------------------------------------------

export function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtFloat(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
}

export function fmtMs(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (v >= 1000) return `${(v / 1000).toFixed(2)}s`;
  return `${Math.round(v)}ms`;
}

export function fmtSeconds(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v.toFixed(1)}s`;
}

export function fmtBytes(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (v < 1024) return `${v} B`;
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
  return `${(v / (1024 * 1024)).toFixed(1)} MB`;
}

/** Relative time like "12s ago" / "3m ago"; falls back to absolute date. */
export function fmtAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "—";
  const diff = Date.now() - t;
  if (diff < 0) return "just now";
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "—";
  return new Date(t).toLocaleTimeString();
}

// ---- Layout primitives ------------------------------------------------------

export function Panel({
  title,
  subtitle,
  right,
  children,
  className = "",
  tourId,
}: {
  title: string;
  subtitle?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  tourId?: string;
}) {
  return (
    <section
      data-tour={tourId}
      className={`flex flex-col rounded-xl border border-white/5 bg-bg-panel shadow-lg shadow-black/30 ${className}`}
    >
      <header className="flex items-start justify-between gap-2 border-b border-white/5 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold tracking-wide text-slate-100">
            {title}
          </h2>
          {subtitle ? (
            <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>
          ) : null}
        </div>
        {right ? <div className="shrink-0">{right}</div> : null}
      </header>
      <div className="flex-1 p-4">{children}</div>
    </section>
  );
}

export function StatCard({
  label,
  value,
  sub,
  accent = "default",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  accent?: "default" | "green" | "red" | "amber" | "purple";
}) {
  const accentText: Record<string, string> = {
    default: "text-slate-100",
    green: "text-accent-green",
    red: "text-accent-red",
    amber: "text-accent-amber",
    purple: "text-accent-purple",
  };
  return (
    <div className="rounded-lg border border-white/5 bg-bg-elevated px-3 py-2.5">
      <div className="text-[11px] uppercase tracking-wide text-slate-400">
        {label}
      </div>
      <div className={`mt-1 text-xl font-semibold ${accentText[accent]}`}>
        {value}
      </div>
      {sub ? <div className="mt-0.5 text-xs text-slate-400">{sub}</div> : null}
    </div>
  );
}

export function Badge({
  children,
  tone = "slate",
}: {
  children: ReactNode;
  tone?: "slate" | "green" | "red" | "amber" | "purple" | "blue";
}) {
  const tones: Record<string, string> = {
    slate: "bg-slate-700/40 text-slate-300 border-slate-600/40",
    green: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    red: "bg-red-500/15 text-red-300 border-red-500/30",
    amber: "bg-amber-500/15 text-amber-300 border-amber-500/30",
    purple: "bg-violet-500/15 text-violet-300 border-violet-500/30",
    blue: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full min-h-[80px] items-center justify-center rounded-lg border border-dashed border-white/10 p-4 text-center text-sm text-slate-500">
      {children}
    </div>
  );
}
