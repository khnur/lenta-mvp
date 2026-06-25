/**
 * Lightweight, dependency-free onboarding for the Lenta dashboard.
 *
 * Two pieces, both purely additive (they overlay the app and never change how
 * the live panels behave):
 *   1. A one-time **welcome** card that introduces the product.
 *   2. A **guided spotlight tour** that highlights each panel in turn with a
 *      short "what is this / what to look for" explanation.
 *
 * Targets are matched by a `data-tour="..."` attribute on existing elements, so
 * adding/removing steps never requires touching layout. State of "have I seen
 * this" lives in localStorage, and the tour can be relaunched any time from the
 * header button via `useOnboarding().start()`.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";

const SEEN_KEY = "lenta_onboarding_seen_v1";

type Step = {
  target: string | null; // data-tour value; null => centered (no spotlight)
  title: string;
  body: ReactNode;
};

const STEPS: Step[] = [
  {
    target: "tour-status",
    title: "Your system at a glance",
    body: "These pills are Lenta's live pulse — the active model version, total events ingested, whether the simulator is running (and how fast), plus database and cache health. Everything refreshes every 2 seconds.",
  },
  {
    target: "tour-report",
    title: "What changed — in plain English",
    body: "After each retrain, Lenta tells you what actually moved: which genres rose or fell in people's feeds, and how ranking quality (NDCG / recall) shifted. Glance here first to understand the newest model.",
  },
  {
    target: "tour-workflow",
    title: "How one feed is built",
    body: "Every recommendation flows through four stages — Catalog → Candidates → Ranked → Feed. Pick any user from the dropdown to watch their personalized feed, the live event stream, and active sessions update in real time.",
  },
  {
    target: "tour-timeline",
    title: "A model that keeps learning",
    body: "Each retrain ships a new model version. The timeline tracks ranking quality across versions, so you can watch the system improve — and bounce back after a shock — without leaving the page.",
  },
  {
    target: "tour-ab",
    title: "Proof it works: the A/B test",
    body: "Half of traffic (control) gets a plain popularity feed; the other half (treatment) gets Lenta's recommender. The lift shows how much more people click and watch when recommendations are personalized.",
  },
  {
    target: "tour-scenarios",
    title: "The demo cockpit",
    body: "This is where you drive the simulation. Start or stop synthetic traffic, dial the intensity, and inject real-world scenarios — a shift in tastes, a surge of new uploads, or a wave of brand-new users.",
  },
  {
    target: "tour-demo",
    title: "Try the 2-click demo",
    body: "The fastest way to see Lenta adapt: ① trigger a genre shift, then ② retrain. Watch the “What changed” banner and the A/B lift respond as the model relearns. That's the whole loop — enjoy exploring!",
  },
];

type Ctx = { start: () => void; seen: boolean };
const OnboardingCtx = createContext<Ctx>({ start: () => {}, seen: true });

export function useOnboarding(): Ctx {
  return useContext(OnboardingCtx);
}

type Phase = "closed" | "welcome" | "tour";

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>("closed");
  const [idx, setIdx] = useState(0);
  const [seen, setSeen] = useState(true);

  // First visit → auto-open the welcome card.
  useEffect(() => {
    let already = true;
    try {
      already = Boolean(localStorage.getItem(SEEN_KEY));
    } catch {
      already = false;
    }
    setSeen(already);
    if (!already) setPhase("welcome");
  }, []);

  const markSeen = useCallback(() => {
    try {
      localStorage.setItem(SEEN_KEY, "1");
    } catch {
      /* ignore (private mode etc.) */
    }
    setSeen(true);
  }, []);

  const finish = useCallback(() => {
    markSeen();
    setPhase("closed");
    setIdx(0);
  }, [markSeen]);

  const start = useCallback(() => {
    setIdx(0);
    setPhase("welcome");
  }, []);

  const startTour = useCallback(() => {
    setIdx(0);
    setPhase("tour");
  }, []);

  const next = useCallback(() => {
    setIdx((i) => {
      if (i >= STEPS.length - 1) {
        finish();
        return i;
      }
      return i + 1;
    });
  }, [finish]);

  const prev = useCallback(() => setIdx((i) => Math.max(0, i - 1)), []);

  return (
    <OnboardingCtx.Provider value={{ start, seen }}>
      {children}
      {phase === "welcome" && (
        <Welcome onStart={startTour} onSkip={finish} />
      )}
      {phase === "tour" && (
        <Spotlight
          step={STEPS[idx]}
          idx={idx}
          total={STEPS.length}
          onPrev={prev}
          onNext={next}
          onClose={finish}
        />
      )}
    </OnboardingCtx.Provider>
  );
}

// --------------------------------------------------------------------------- //
// Focus management for the modal overlays                                     //
// --------------------------------------------------------------------------- //
const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]';

/**
 * Make a container behave like a proper modal dialog (per the ARIA `dialog`
 * pattern): move focus inside on open, wrap Tab/Shift+Tab within it, and
 * restore focus to wherever it was when the dialog closes.
 */
function useFocusTrap(ref: RefObject<HTMLElement>) {
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const prev = document.activeElement as HTMLElement | null;

    const focusable = () =>
      Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.tabIndex >= 0 && el.offsetParent !== null
      );

    const initial =
      node.querySelector<HTMLElement>("[data-autofocus]") ?? focusable()[0] ?? node;
    initial.focus();

    function onKey(e: KeyboardEvent) {
      if (e.key !== "Tab") return;
      const items = focusable();
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    node.addEventListener("keydown", onKey);
    return () => {
      node.removeEventListener("keydown", onKey);
      // Return focus to the trigger so it isn't dropped to the top of the page.
      if (prev && typeof prev.focus === "function") prev.focus();
    };
  }, [ref]);
}

// --------------------------------------------------------------------------- //
// Welcome card                                                                //
// --------------------------------------------------------------------------- //
function Welcome({ onStart, onSkip }: { onStart: () => void; onSkip: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(ref);
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onSkip();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onSkip]);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onSkip} />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label="Welcome to Lenta"
        tabIndex={-1}
        className="relative z-[101] w-full max-w-lg rounded-2xl border border-white/10 bg-bg-panel p-6 shadow-2xl shadow-black/60 focus:outline-none"
      >
        <div className="mb-1 flex items-center gap-2">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500/30 to-violet-500/20 text-lg">
            ✨
          </span>
          <h2 className="text-lg font-bold tracking-tight text-slate-50">
            Welcome to Lenta
          </h2>
        </div>
        <p className="mt-2 text-sm leading-relaxed text-slate-300">
          A live, self-learning video recommender — this dashboard shows the
          whole system working in real time. There's a lot on screen, so here's a
          quick 60-second tour of what each panel means and how to drive the demo.
        </p>

        <ul className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {[
            ["🎯", "Personalized feeds, built live"],
            ["🔁", "A model that retrains itself"],
            ["🧪", "A/B proof vs. a popularity baseline"],
            ["🎮", "A cockpit to simulate real scenarios"],
          ].map(([icon, label]) => (
            <li
              key={label}
              className="flex items-center gap-2 rounded-lg border border-white/5 bg-bg-elevated px-3 py-2 text-xs text-slate-300"
            >
              <span>{icon}</span>
              {label}
            </li>
          ))}
        </ul>

        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            onClick={onSkip}
            className="rounded-md px-3 py-2 text-sm font-medium text-slate-400 transition hover:text-slate-200"
          >
            Explore on my own
          </button>
          <button
            onClick={onStart}
            data-autofocus
            className="rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white shadow transition hover:bg-sky-500"
          >
            Take the tour →
          </button>
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Spotlight tour                                                              //
// --------------------------------------------------------------------------- //
type Rect = { top: number; left: number; width: number; height: number };

function Spotlight({
  step,
  idx,
  total,
  onPrev,
  onNext,
  onClose,
}: {
  step: Step;
  idx: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
}) {
  const [rect, setRect] = useState<Rect | null>(null);
  const ttRef = useRef<HTMLDivElement>(null);
  useFocusTrap(ttRef);

  // Measure the current target (and keep it fresh on scroll/resize).
  useLayoutEffect(() => {
    let raf = 0;
    function measure() {
      if (!step.target) {
        setRect(null);
        return;
      }
      const el = document.querySelector<HTMLElement>(
        `[data-tour="${step.target}"]`
      );
      if (!el) {
        setRect(null);
        return;
      }
      const r = el.getBoundingClientRect();
      setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
    }
    function schedule() {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(measure);
    }
    // Bring the target into view first, then measure.
    if (step.target) {
      const el = document.querySelector<HTMLElement>(
        `[data-tour="${step.target}"]`
      );
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    measure();
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true);
    // Re-measure for a moment while smooth-scroll settles.
    const t1 = window.setTimeout(measure, 180);
    const t2 = window.setTimeout(measure, 420);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", schedule, true);
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [step.target]);

  // Keyboard navigation. Enter/Space are left to the focused button (which the
  // focus trap selects on open) so a single keypress never advances twice.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight") onNext();
      else if (e.key === "ArrowLeft") onPrev();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, onNext, onPrev]);

  const vw = typeof window !== "undefined" ? window.innerWidth : 1280;
  const vh = typeof window !== "undefined" ? window.innerHeight : 800;
  const PAD = 8;
  const TT_W = Math.min(360, vw - 24);
  const TT_H = 232;

  // Tooltip position: prefer below the target, flip above if it would overflow,
  // and clamp inside the viewport. Centered when there's no target.
  let ttTop: number;
  let ttLeft: number;
  if (rect) {
    ttTop = rect.top + rect.height + PAD + 8;
    if (ttTop + TT_H > vh - 12) ttTop = rect.top - PAD - 8 - TT_H;
    ttTop = clamp(ttTop, 12, vh - TT_H - 12);
    ttLeft = clamp(rect.left + rect.width / 2 - TT_W / 2, 12, vw - TT_W - 12);
  } else {
    ttTop = vh / 2 - TT_H / 2;
    ttLeft = vw / 2 - TT_W / 2;
  }

  return (
    <div className="fixed inset-0 z-[100]">
      {/* Click shield: keeps panels non-interactive during the tour. */}
      <button
        aria-label="Skip tour"
        onClick={onClose}
        className="absolute inset-0 h-full w-full cursor-default"
        tabIndex={-1}
      />

      {/* Spotlight cutout (the huge box-shadow dims everything else). */}
      {rect ? (
        <div
          className="pointer-events-none absolute rounded-xl ring-2 ring-sky-400/90 transition-all duration-300 ease-out"
          style={{
            top: rect.top - PAD,
            left: rect.left - PAD,
            width: rect.width + PAD * 2,
            height: rect.height + PAD * 2,
            boxShadow: "0 0 0 9999px rgba(2,6,12,0.74)",
          }}
        />
      ) : (
        <div className="pointer-events-none absolute inset-0 bg-black/70" />
      )}

      {/* Tooltip card */}
      <div
        ref={ttRef}
        role="dialog"
        aria-modal="true"
        aria-label={step.title}
        tabIndex={-1}
        className="pointer-events-auto absolute w-[360px] max-w-[calc(100vw-24px)] rounded-xl border border-white/10 bg-bg-panel p-4 shadow-2xl shadow-black/60 transition-all duration-300 ease-out focus:outline-none"
        style={{ top: ttTop, left: ttLeft, width: TT_W }}
      >
        <div className="mb-1 flex items-center justify-between gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-sky-300">
            Step {idx + 1} of {total}
          </span>
          <button
            onClick={onClose}
            className="text-xs text-slate-500 transition hover:text-slate-300"
          >
            Skip
          </button>
        </div>
        <h3 className="text-base font-semibold text-slate-50">{step.title}</h3>
        <p className="mt-1.5 text-sm leading-relaxed text-slate-300">
          {step.body}
        </p>

        {/* progress dots */}
        <div className="mt-3 flex items-center gap-1.5">
          {Array.from({ length: total }).map((_, i) => (
            <span
              key={i}
              className={`h-1.5 rounded-full transition-all ${
                i === idx ? "w-5 bg-sky-400" : "w-1.5 bg-slate-600"
              }`}
            />
          ))}
        </div>

        <div className="mt-4 flex items-center justify-between gap-2">
          <button
            onClick={onPrev}
            disabled={idx === 0}
            className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-300 transition hover:text-white disabled:cursor-not-allowed disabled:opacity-30"
          >
            ← Back
          </button>
          <button
            onClick={onNext}
            data-autofocus
            className="rounded-md bg-sky-600 px-4 py-1.5 text-sm font-semibold text-white shadow transition hover:bg-sky-500"
          >
            {idx === total - 1 ? "Done ✓" : "Next →"}
          </button>
        </div>
      </div>
    </div>
  );
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(Math.max(v, lo), Math.max(lo, hi));
}
