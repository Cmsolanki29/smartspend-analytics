import React, { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  Bell,
  Cpu,
  GitBranch,
  Layers,
  LineChart,
  MapPin,
  Network,
  RefreshCw,
  Search,
  Shield,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  UserCircle,
  Workflow,
  Zap,
} from "lucide-react";
import { getFraudShieldAnalyze, getFraudShieldStats } from "../../services/api";
import { ErrorCard } from "../common/ErrorCard";
import { SkeletonCard } from "../common/SkeletonCard";
import { inr } from "../../lib/format";
import { FRAUD_SHIELD_PHASES } from "./fraudshieldPhases";
import FraudEducation from "./FraudEducation";
import FraudAlertsList from "./FraudAlertsList";
import FraudStats from "./FraudStats";
import TransactionChecker from "./TransactionChecker";
import FraudShieldLiveEventsTab from "./FraudShieldLiveEventsTab";
import InvestigationConsole from "./InvestigationConsole";
import { PhaseCard } from "./PhaseCard";
import { PhaseFlowBackdrop } from "./PhaseFlowBackdrop";
import { TrustRing } from "./TrustRing";
import { MiniSparkline } from "./MiniSparkline";
import { useCountUp } from "./useCountUp";

const ICON_MAP = {
  Zap,
  Layers,
  LineChart,
  Shield,
  Activity,
  GitBranch,
  Sparkles,
  RefreshCw,
  Search,
  Network,
  Cpu,
  Workflow,
};

const TABS = [
  { id: "overview", label: "Overview", Icon: Shield },
  { id: "alerts", label: "Alerts", Icon: Bell },
  { id: "behavior", label: "Behavior", Icon: UserCircle },
  { id: "devices", label: "Devices", Icon: MapPin },
  { id: "investigations", label: "Investigations", Icon: Search },
  { id: "live", label: "Live events", Icon: Activity },
];

const TAB_IDS = new Set(TABS.map((t) => t.id));

const AlertsCenter = lazy(() => import("../../pages/risk/AlertsCenter"));
const BehaviorProfile = lazy(() => import("../../pages/risk/BehaviorProfile"));
const DeviceTrust = lazy(() => import("../../pages/risk/DeviceTrust"));
const InvestigationViewer = lazy(() => import("../../pages/risk/InvestigationViewer"));
const AIPerformance = lazy(() => import("../../pages/risk/AIPerformance"));
const GNNTrainingPanel = lazy(() => import("../../pages/risk/GNNTrainingPanel"));
const DNNShadowReport = lazy(() => import("../../pages/risk/DNNShadowReport"));
const OrchestratorDashboard = lazy(() => import("../../pages/risk/OrchestratorDashboard"));

const tabFallback = (
  <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-8">
    <SkeletonCard lines={4} height={120} />
  </div>
);

const legacyNavigate = (setTab) => (legacyId) => {
  const m = {
    "trust-center": "overview",
    "alerts-center": "alerts",
    "behavior-profile": "behavior",
    "device-trust": "devices",
    "investigations": "investigations",
    "ai-performance": "overview",
    "gnn-training": "overview",
    "dnn-shadow": "overview",
    "orchestrator": "overview",
  };
  setTab(m[legacyId] || "overview");
};

function PhaseShowcase() {
  return (
    <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-br from-[#0a0a1f]/90 via-violet-950/30 to-[#0f172a]/90 p-6 shadow-[0_0_60px_-20px_rgba(124,58,237,0.35)] backdrop-blur-xl md:p-8">
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.12]"
        style={{
          backgroundImage:
            "radial-gradient(circle at 20% 20%, rgba(124,58,237,0.5), transparent 45%), radial-gradient(circle at 80% 60%, rgba(37,99,235,0.35), transparent 40%)",
        }}
      />
      <PhaseFlowBackdrop />
      <div className="relative mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-violet-300/80">12-Phase AI protection stack</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-white md:text-3xl">FraudShield control room</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-exiqo-glow/70">
            Twelve independent layers score, explain, and escalate risk before money moves. One surface — the same bar as
            enterprise fraud stacks, tuned for clarity.
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-emerald-500/40 bg-emerald-500/15 px-4 py-2 shadow-[0_0_24px_-8px_rgba(16,185,129,0.5)]">
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400" />
          </span>
          <span className="text-xs font-bold uppercase tracking-wide text-emerald-200">🛡 All 12 layers active</span>
        </div>
      </div>

      <div className="relative mb-4 hidden h-px w-full overflow-hidden rounded-full bg-gradient-to-r from-transparent via-white/25 to-transparent md:block" aria-hidden>
        <motion.div
          className="h-full w-1/3 bg-gradient-to-r from-violet-400 to-cyan-400"
          animate={{ x: ["-100%", "400%"] }}
          transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
        />
      </div>

      <div className="relative grid snap-x snap-mandatory grid-flow-col auto-cols-[minmax(148px,1fr)] gap-3 overflow-x-auto pb-2 md:grid-flow-row md:grid-cols-3 lg:grid-cols-4 md:overflow-visible">
        {FRAUD_SHIELD_PHASES.map((ph, idx) => {
          const Ico = ICON_MAP[ph.icon] || Shield;
          return <PhaseCard key={ph.key} phase={ph} Icon={Ico} index={idx} />;
        })}
      </div>
    </div>
  );
}

function StatStrip({ safetyScore, blocked, saved, loading, error, onRetry }) {
  const safetyAnim = useCountUp(safetyScore, { durationMs: 1100 });
  const blockedAnim = useCountUp(blocked, { durationMs: 1000 });
  const savedAnim = useCountUp(saved, { durationMs: 1100 });

  if (loading) {
    return (
      <div className="mb-6 grid gap-3 md:grid-cols-3">
        <SkeletonCard lines={2} height={88} />
        <SkeletonCard lines={2} height={88} />
        <SkeletonCard lines={2} height={88} />
      </div>
    );
  }
  if (error) {
    return (
      <div className="mb-6">
        <ErrorCard message={error} onRetry={onRetry} />
      </div>
    );
  }

  const cards = [
    {
      key: "safety",
      label: "Safety score",
      tone: "from-violet-600/30 to-blue-600/20 border-violet-500/30",
      body: (
        <div className="mt-1 flex flex-wrap items-center gap-4">
          <TrustRing score={safetyAnim} max={100} size={100} stroke={7} label="Score" />
          <p className="max-w-[10rem] text-xs leading-relaxed text-exiqo-glow/60">
            Blended model + rules confidence on your last 30 days of activity.
          </p>
        </div>
      ),
    },
    {
      key: "blocked",
      label: "Threats blocked",
      tone: "from-rose-600/25 to-orange-600/15 border-rose-500/25",
      body: (
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          <p className="text-3xl font-bold tabular-nums tracking-tight text-white">{Math.round(blockedAnim)}</p>
          <MiniSparkline seed={blocked} className="opacity-90" />
          <p className="w-full text-xs text-exiqo-glow/60">This month · FraudShield + bank rules</p>
        </div>
      ),
    },
    {
      key: "saved",
      label: "Money saved",
      tone: "from-emerald-600/30 to-teal-600/15 border-emerald-500/30",
      body: (
        <div className="mt-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-2xl font-bold tabular-nums tracking-tight text-white sm:text-3xl">
              {inr(Math.round(savedAnim))}
            </p>
            <span className="inline-flex items-center gap-0.5 rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase text-emerald-200/90">
              <TrendingUp className="h-3 w-3" aria-hidden />
              Trend
            </span>
          </div>
          <p className="mt-1 text-xs text-exiqo-glow/60">Disputes + prevented loss (rolling)</p>
        </div>
      ),
    },
  ];

  return (
    <div className="mb-6 grid gap-3 md:grid-cols-3">
      {cards.map((c, i) => (
        <motion.div
          key={c.key}
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.06, duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
          whileHover={{ y: -2, transition: { duration: 0.15 } }}
          className={`rounded-2xl border bg-gradient-to-br p-6 ${c.tone} backdrop-blur-md shadow-[0_0_32px_-18px_rgba(124,58,237,0.35)] transition-shadow duration-300 hover:shadow-[0_0_44px_-12px_rgba(124,58,237,0.45)]`}
        >
          <p className="text-[10px] font-semibold uppercase tracking-wider text-white/50">{c.label}</p>
          {c.body}
        </motion.div>
      ))}
    </div>
  );
}

const FraudShieldPage = ({ userId, userName }) => {
  const readInitialTab = () => {
    try {
      const q = new URLSearchParams(window.location.search).get("fraudTab");
      if (q && TAB_IDS.has(q)) return q;
    } catch {
      /* ignore */
    }
    return "overview";
  };

  const [tab, setTab] = useState(readInitialTab);
  const [stats, setStats] = useState(null);
  const [analyze, setAnalyze] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [alertsTick, setAlertsTick] = useState(0);
  const [diagOpen, setDiagOpen] = useState(false);

  const displayName = userName || "User";
  const onLegacyNav = useMemo(() => legacyNavigate(setTab), []);

  useEffect(() => {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("fraudTab", tab);
      window.history.replaceState({}, "", url.toString());
    } catch {
      /* ignore */
    }
  }, [tab]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setStats(null);
    setAnalyze(null);
    try {
      const s = await getFraudShieldStats(userId);
      setStats(s);
    } catch (e) {
      setError(e.message || "Failed to load stats");
    }
    try {
      const a = await getFraudShieldAnalyze(userId);
      setAnalyze(a);
    } catch {
      setAnalyze(null);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    load();
  }, [load, alertsTick]);

  /** Sync tab when URL `fraudTab` changes without remount (e.g. mastery rail). */
  useEffect(() => {
    const sync = () => {
      try {
        const q = new URLSearchParams(window.location.search).get("fraudTab");
        if (q && TAB_IDS.has(q)) setTab((prev) => (prev === q ? prev : q));
      } catch {
        /* ignore */
      }
    };
    window.addEventListener("focus", sync);
    return () => window.removeEventListener("focus", sync);
  }, []);

  const onAlertsChanged = () => setAlertsTick((t) => t + 1);

  const safetyScore = stats?.safety_score ?? 0;
  const blocked = stats?.threats_blocked ?? 0;
  const saved = stats?.money_saved_total ?? 0;

  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-8">
      <PhaseShowcase />

      <StatStrip
        safetyScore={safetyScore}
        blocked={blocked}
        saved={saved}
        loading={loading}
        error={error}
        onRetry={load}
      />

      <div className="flex flex-wrap gap-2 rounded-2xl border border-white/10 bg-white/[0.03] p-2 backdrop-blur-xl">
        {TABS.map((t) => {
          const I = t.Icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`inline-flex min-h-[44px] items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50 ${
                active
                  ? "bg-gradient-to-r from-violet-600 to-blue-600 text-white shadow-[0_0_28px_-8px_rgba(124,58,237,0.55)]"
                  : "text-exiqo-glow/75 hover:bg-white/[0.06] hover:text-white"
              }`}
            >
              <I className="h-4 w-4 shrink-0 opacity-90" aria-hidden />
              {t.label}
            </button>
          );
        })}
      </div>

      <AnimatePresence mode="wait">
        <motion.section
          key={tab}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.22 }}
          className="rounded-3xl border border-white/[0.08] bg-white/[0.02] p-5 shadow-[0_0_50px_-24px_rgba(124,58,237,0.35)] backdrop-blur-xl sm:p-7"
        >
          {tab === "overview" && (
            <div className="space-y-8">
              <div>
                <div className="mb-4 flex items-center gap-2">
                  <ShieldCheck className="h-5 w-5 text-emerald-300" aria-hidden />
                  <h2 className="text-lg font-bold text-white">Real-time transaction safety checker</h2>
                </div>
                <TransactionChecker userId={userId} userName={displayName} onReportSuccess={onAlertsChanged} />
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                  <h3 className="text-sm font-bold text-white">Fraud awareness</h3>
                  <p className="mb-3 text-xs text-exiqo-glow/65">Swipe cards — same education module as before, polished container.</p>
                  <FraudEducation />
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                  <h3 className="text-sm font-bold text-white">Your protection stats</h3>
                  <p className="mb-3 text-xs text-exiqo-glow/65">Detailed breakdown from FraudShield analytics.</p>
                  <FraudStats userId={userId} />
                </div>
              </div>

              <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.02] p-4">
                <button
                  type="button"
                  onClick={() => setDiagOpen((o) => !o)}
                  className="flex w-full items-center justify-between text-left text-sm font-semibold text-exiqo-glow/80 hover:text-white"
                >
                  <span>Engine diagnostics (ops / demo)</span>
                  <span className="text-xs text-exiqo-glow/50">{diagOpen ? "Hide" : "Show"}</span>
                </button>
                {diagOpen ? (
                  <div className="mt-4 space-y-6 border-t border-white/10 pt-4">
                    <p className="text-xs text-exiqo-glow/60">
                      Internal ML consoles — previously separate sidebar items. Not required for day-to-day banking.
                    </p>
                    <Suspense fallback={tabFallback}>
                      <AIPerformance />
                    </Suspense>
                    <Suspense fallback={tabFallback}>
                      <GNNTrainingPanel />
                    </Suspense>
                    <Suspense fallback={tabFallback}>
                      <DNNShadowReport />
                    </Suspense>
                    <Suspense fallback={tabFallback}>
                      <OrchestratorDashboard />
                    </Suspense>
                  </div>
                ) : null}
              </div>
            </div>
          )}

          {tab === "alerts" && (
            <div className="space-y-4">
              <h2 className="text-lg font-bold text-white">Alerts & review queue</h2>
              <p className="text-sm text-exiqo-glow/65">
                Phase 8 review queue with Phase 9 investigation hooks — same backend, unified surface.
              </p>
              <Suspense fallback={tabFallback}>
                <AlertsCenter userId={userId} />
              </Suspense>
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <h3 className="mb-2 text-sm font-semibold text-white">FraudShield alerts (consumer)</h3>
                <FraudAlertsList userId={userId} onAlertsChanged={onAlertsChanged} />
              </div>
            </div>
          )}

          {tab === "behavior" && (
            <div className="space-y-4">
              <h2 className="text-lg font-bold text-white">Behaviour profile</h2>
              <p className="text-sm text-exiqo-glow/65">Login cadence, geo signals, and anomaly list — ported from the old Behaviour Profile page.</p>
              <Suspense fallback={tabFallback}>
                <BehaviorProfile userId={userId} onNavigate={onLegacyNav} />
              </Suspense>
            </div>
          )}

          {tab === "devices" && (
            <div className="space-y-4">
              <Suspense fallback={tabFallback}>
                <DeviceTrust userId={userId} onNavigate={onLegacyNav} embedded />
              </Suspense>
            </div>
          )}

          {tab === "investigations" && (
            <div className="space-y-4">
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <h2 className="text-lg font-bold text-white">AI investigations</h2>
                <p className="mt-2 max-w-3xl text-sm leading-relaxed text-exiqo-glow/75">
                  Our AI investigator (Phase 9) analyses every high-risk transaction the way a fraud analyst would — merchant
                  velocity, your spend curve, graph signals, and similar past frauds. Use <strong className="text-white">Run investigation</strong>{" "}
                  below to watch a live-style trace, then review real queue items.
                </p>
              </div>
              <InvestigationConsole />
              <Suspense fallback={tabFallback}>
                <InvestigationViewer userId={userId} />
              </Suspense>
            </div>
          )}

          {tab === "live" && (
            <div className="space-y-4">
              <h2 className="text-lg font-bold text-white">Live events</h2>
              <p className="text-sm text-exiqo-glow/65">Stream of scored events — demo ticker until WebSocket feed lands.</p>
              <FraudShieldLiveEventsTab userId={userId} />
            </div>
          )}
        </motion.section>
      </AnimatePresence>

      {analyze?.summary ? (
        <p className="text-center text-[11px] text-exiqo-glow/40">Analysis hint: {String(analyze.summary).slice(0, 160)}…</p>
      ) : null}
    </div>
  );
};

export default FraudShieldPage;
