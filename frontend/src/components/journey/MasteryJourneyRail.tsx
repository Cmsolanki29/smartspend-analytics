import React, { memo, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Check, ChevronRight, Cpu, Zap } from "lucide-react";
import { GlassCard } from "../intro/GlassCard";
import { getMasteryPhase, MASTERY_PHASES, CATEGORY_LABELS } from "./masteryPhases";

const clampPhase = (n: number) => Math.min(12, Math.max(1, Math.floor(n) || 1));

/** Box-shadow for the breathing ring on the active journey-progress node. Per category. */
const CURRENT_SHADOW: Record<string, string> = {
  data:         "0 0 0 1.5px rgba(34,211,238,0.50), 0 0 20px rgba(34,211,238,0.28)",
  model:        "0 0 0 1.5px rgba(124,58,237,0.55), 0 0 22px rgba(124,58,237,0.32)",
  intelligence: "0 0 0 1.5px rgba(236,72,153,0.55), 0 0 22px rgba(236,72,153,0.30)",
  ops:          "0 0 0 1.5px rgba(167,139,250,0.50), 0 0 20px rgba(167,139,250,0.28)",
};

/** Breathing ring class for current node. */
const CURRENT_RING_CLASS: Record<string, string> = {
  data:         "border-ss-cyan/65",
  model:        "border-exiqo-purple/70",
  intelligence: "border-exiqo-pink/70",
  ops:          "border-exiqo-glow/65",
};

/** Colored number class for the active journey-progress node. */
const CURRENT_NUM_CLASS: Record<string, string> = {
  data:         "text-ss-cyan",
  model:        "text-exiqo-glow",
  intelligence: "text-exiqo-pink",
  ops:          "text-exiqo-glow",
};

export type MasteryJourneyRailProps = {
  /** Active journey phase (1–12). Phases before this are completed. */
  currentPhase: number;
  journeyComplete?: boolean;
  onNavigateToTab: (tabId: string) => void;
  onAdvancePhase?: () => void;
  /** Currently open app tab — used to highlight phases that belong to this section. */
  activeTab?: string;
};

/* ─────────────────────── Connector ─────────────────────── */
type ConnectorProps = { filled: boolean; reduce: boolean; staggerIndex: number };

const Connector = memo(function Connector({ filled, reduce, staggerIndex }: ConnectorProps) {
  return (
    <div
      className="relative mx-[3px] h-[2px] min-w-[4px] flex-1 self-center rounded-full bg-white/[0.07]"
      aria-hidden
    >
      <motion.div
        className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-exiqo-purple via-exiqo-pink to-ss-cyan"
        style={{ transformOrigin: "left center" }}
        initial={false}
        animate={{ scaleX: filled ? 1 : 0, opacity: filled ? 1 : 0.25 }}
        transition={{
          duration: reduce ? 0.1 : 0.55,
          delay: reduce ? 0 : Math.min(staggerIndex, 8) * 0.028,
          ease: [0.22, 1, 0.36, 1],
        }}
      />
    </div>
  );
});

/* ─────────────────────── Node ─────────────────────── */
type NodeProps = {
  phase: number;
  state: "locked" | "current" | "completed";
  category: string;
  /** Whether this phase's tabId matches the currently open app tab. */
  isTabRelated: boolean;
  reduce: boolean;
  showBurst: boolean;
  isCurrentStep: boolean;
  title: string;
  detailOpen: boolean;
  detailPanelId: string;
  onSelect: (phase: number) => void;
  onOpenWorkspace: () => void;
};

const Node = memo(function Node({
  phase,
  state,
  category,
  isTabRelated,
  reduce,
  showBurst,
  isCurrentStep,
  title,
  detailOpen,
  detailPanelId,
  onSelect,
  onOpenWorkspace,
}: NodeProps) {
  const isCurrent = state === "current";
  const isDone    = state === "completed";
  const isLocked  = state === "locked";

  const ringClass     = CURRENT_RING_CLASS[category]  ?? "border-exiqo-glow/65";
  const shadowStyle   = CURRENT_SHADOW[category]      ?? "";
  const numColorClass = CURRENT_NUM_CLASS[category]   ?? "text-exiqo-glow";

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpenWorkspace(); }
  };

  return (
    <div className="relative flex shrink-0 items-center justify-center" style={{ width: 44, height: 44 }}>
      <motion.button
        type="button"
        aria-current={isCurrentStep ? "step" : undefined}
        aria-expanded={detailOpen}
        aria-controls={detailPanelId}
        aria-label={`Phase ${phase} of 12: ${title}${isCurrent ? " — active" : isDone ? " — complete" : " — pending"}`}
        onClick={() => { onSelect(phase); onOpenWorkspace(); }}
        onKeyDown={handleKeyDown}
        whileHover={{ scale: 1.12 }}
        whileTap={{ scale: 0.95 }}
        transition={{ type: "spring", stiffness: 420, damping: 26 }}
        className={`relative flex h-11 w-11 items-center justify-center rounded-full border outline-none transition-colors duration-200 ease-brand focus-visible:ring-2 focus-visible:ring-cyan-400/50 focus-visible:ring-offset-2 focus-visible:ring-offset-[#070418]
          ${isDone
            ? "border-transparent bg-white/[0.04]"
            : isCurrent
              ? "border-transparent bg-white/[0.04]"
              : isTabRelated
                ? "border-ss-cyan/35 bg-ss-cyan/[0.05]"
                : "border-white/[0.1] bg-white/[0.02] hover:border-white/25 hover:bg-white/[0.05]"
          }`}
        style={{ boxShadow: isCurrent ? shadowStyle : undefined }}
      >
        {/* ── Completed fill ── */}
        {isDone && (
          <span className="absolute inset-[2px] flex items-center justify-center rounded-full bg-gradient-to-br from-exiqo-purple to-exiqo-pink">
            <Check className="h-3.5 w-3.5 text-white" strokeWidth={2.8} aria-hidden />
          </span>
        )}

        {/* ── Current: breathing outer ring ── */}
        {isCurrent && !reduce && (
          <motion.span
            className={`pointer-events-none absolute inset-[-3px] rounded-full border-2 ${ringClass}`}
            animate={{ opacity: [0.4, 0.9, 0.4], scale: [1, 1.06, 1] }}
            transition={{ duration: 2.8, repeat: Infinity, ease: [0.22, 1, 0.36, 1] }}
            aria-hidden
          />
        )}
        {isCurrent && reduce && (
          <span className={`pointer-events-none absolute inset-[-3px] rounded-full border-2 ${ringClass}`} aria-hidden />
        )}

        {/* ── Tab-related indicator dot (bottom of node) ── */}
        {isTabRelated && !isCurrent && !isDone && (
          <span
            className="pointer-events-none absolute bottom-[-5px] left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-ss-cyan/80"
            aria-hidden
          />
        )}
        {isTabRelated && isDone && (
          <span
            className="pointer-events-none absolute bottom-[-5px] left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-ss-cyan/60"
            aria-hidden
          />
        )}

        {/* ── Phase number ── */}
        <span
          className={`relative z-[1] font-heading text-[13px] font-semibold tabular-nums transition-colors duration-200 ${
            isDone
              ? "sr-only"
              : isCurrent
                ? numColorClass             // colored per category — tells user "you are here"
                : isTabRelated
                  ? "text-ss-cyan/80"       // section-related: cyan tint
                  : isLocked
                    ? "text-white/25"
                    : "text-white/70"
          }`}
        >
          {phase}
        </span>

        {/* ── Completion burst ── */}
        {showBurst && !reduce && (
          <motion.span
            className="pointer-events-none absolute inset-[-6px] rounded-full bg-gradient-to-br from-exiqo-purple/55 via-exiqo-pink/35 to-transparent"
            initial={{ opacity: 0.9, scale: 0.85 }}
            animate={{ opacity: 0, scale: 1.28 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            aria-hidden
          />
        )}
        {showBurst && reduce && (
          <motion.span
            className="pointer-events-none absolute inset-0 rounded-full bg-white/10"
            initial={{ opacity: 0 }}
            animate={{ opacity: [0.45, 0] }}
            transition={{ duration: 0.18 }}
            aria-hidden
          />
        )}
      </motion.button>
    </div>
  );
});

/* ─────────────────────── Rail ─────────────────────── */
function MasteryJourneyRailInner({
  currentPhase,
  journeyComplete = false,
  onNavigateToTab,
  onAdvancePhase,
  activeTab,
}: MasteryJourneyRailProps) {
  const reduce  = useReducedMotion();
  const headingId     = useId();
  const detailPanelId = useId();
  const phase  = clampPhase(currentPhase);
  const [burstPhase, setBurstPhase] = useState<number | null>(null);
  const [detailPhase, setDetailPhase] = useState<number | null>(null);
  const prevPhase = useRef<number | null>(null);

  /* Burst animation when journey phase advances */
  useEffect(() => {
    if (journeyComplete) { prevPhase.current = phase; return; }
    if (prevPhase.current === null) { prevPhase.current = phase; return; }
    if (!reduce && phase > prevPhase.current) {
      setBurstPhase(prevPhase.current);
      const id = window.setTimeout(() => setBurstPhase(null), 720);
      prevPhase.current = phase;
      return () => clearTimeout(id);
    }
    prevPhase.current = phase;
  }, [phase, reduce, journeyComplete]);

  const currentMeta  = useMemo(() => getMasteryPhase(journeyComplete ? 12 : phase), [phase, journeyComplete]);
  const displayMeta  = useMemo(
    () => (detailPhase != null ? getMasteryPhase(detailPhase) : null),
    [detailPhase]
  );
  const shownMeta = displayMeta ?? currentMeta;

  /* When active tab changes, clear manual detail selection so the section context auto-shows */
  useEffect(() => { setDetailPhase(null); }, [activeTab]);

  const openWorkspace = useCallback(
    (tabId: string, fraudshieldTab?: string) => {
      onNavigateToTab(tabId);
      if (tabId === "fraud" && fraudshieldTab) {
        try {
          const url = new URL(window.location.href);
          url.searchParams.set("fraudTab", fraudshieldTab);
          window.history.replaceState({}, "", url.toString());
        } catch {
          /* ignore */
        }
      }
    },
    [onNavigateToTab]
  );

  /* Phases related to current workspace tab (FraudShield: no per-phase dot — all layers live in one hub). */
  const tabRelatedPhases = useMemo(() => {
    if (!activeTab || activeTab === "fraud") return new Set<number>();
    return new Set(MASTERY_PHASES.filter((m) => m.tabId === activeTab).map((m) => m.phase));
  }, [activeTab]);

  const completedCount = journeyComplete ? 12 : phase - 1;

  return (
    <GlassCard
      padding="sm"
      elevation="raised"
      className="mb-5 border-white/[0.1] shadow-ss-glass"
      role="region"
      aria-labelledby={headingId}
    >
      {/* ── Header ── */}
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          {/* Small CPU/chip icon — represents AI pipeline, no full ShieldMark here */}
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-exiqo-purple/80 to-exiqo-pink/80">
            <Cpu className="h-4 w-4 text-white" aria-hidden />
          </span>
          <div className="min-w-0">
            <h2
              id={headingId}
              className="font-heading text-[14px] font-semibold tracking-tight text-white sm:text-[15px]"
            >
              AI Risk Intelligence
            </h2>
            <p className="mt-0.5 text-[11px] text-white/40">
              12-layer protection stack &nbsp;·&nbsp;
              <span className="tabular-nums text-exiqo-glow/80">
                {journeyComplete ? "all layers active" : `${completedCount} of 12 active`}
              </span>
            </p>
          </div>
        </div>

        {/* Right: current journey-phase indicator */}
        {currentMeta && !journeyComplete ? (
          <div className="flex shrink-0 items-center gap-1.5 sm:justify-end">
            <Zap className="h-3 w-3 text-exiqo-glow/60" aria-hidden />
            <span className="text-[11px] text-white/55 sm:text-xs">
              Phase{" "}
              <span className="tabular-nums font-semibold text-white">{phase}</span>
              <span className="mx-1 text-white/25">·</span>
              <span className="text-exiqo-glow/85">{currentMeta.title}</span>
            </span>
          </div>
        ) : journeyComplete ? (
          <span className="text-[11px] text-emerald-300/90 sm:text-xs">All 12 layers operational</span>
        ) : null}
      </div>

      {/* ── Phase nodes rail ── */}
      <div
        className="relative -mx-1 px-1 md:mx-0 md:px-0"
        style={{
          maskImage: "linear-gradient(90deg, transparent 0, black 10px, black calc(100% - 10px), transparent 100%)",
          WebkitMaskImage: "linear-gradient(90deg, transparent 0, black 10px, black calc(100% - 10px), transparent 100%)",
        }}
      >
        <nav
          aria-label="12-layer AI risk protection stack"
          className="overflow-x-auto overscroll-x-contain pb-2 snap-x snap-mandatory [-ms-overflow-style:none] [scrollbar-width:none] md:overflow-visible [&::-webkit-scrollbar]:hidden"
        >
          <ol className="flex min-w-[min(100%,620px)] list-none items-center gap-0 px-2 md:min-w-0 md:px-0">
            {MASTERY_PHASES.map((meta, idx) => {
              const n = meta.phase;
              let nodeState: "locked" | "current" | "completed";
              if (journeyComplete || n < phase) nodeState = "completed";
              else if (n === phase && !journeyComplete) nodeState = "current";
              else nodeState = "locked";

              return (
                <li
                  key={meta.phase}
                  className="flex min-w-0 flex-1 snap-center items-center [-webkit-tap-highlight-color:transparent]"
                >
                  {idx > 0 && (
                    <Connector
                      filled={journeyComplete || phase > n - 1}
                      reduce={!!reduce}
                      staggerIndex={idx - 1}
                    />
                  )}
                  <Node
                    phase={n}
                    state={nodeState}
                    category={meta.category}
                    isTabRelated={tabRelatedPhases.has(n)}
                    reduce={!!reduce}
                    showBurst={burstPhase === n}
                    isCurrentStep={!journeyComplete && n === phase}
                    title={meta.title}
                    detailOpen={detailPhase === n}
                    detailPanelId={detailPanelId}
                    onSelect={setDetailPhase}
                    onOpenWorkspace={() => {
                      setDetailPhase(n);
                      openWorkspace(meta.tabId, meta.fraudshieldTab);
                    }}
                  />
                </li>
              );
            })}
          </ol>
        </nav>
      </div>

      {/* ── Legend (tiny) ── */}
      <div className="mt-1 flex items-center gap-4 px-1 pb-0.5">
        <span className="flex items-center gap-1.5 text-[10px] text-white/30">
          <span className="h-1.5 w-1.5 rounded-full bg-gradient-to-r from-exiqo-purple to-exiqo-pink" aria-hidden />
          Completed
        </span>
        <span className="flex items-center gap-1.5 text-[10px] text-white/30">
          <span className="h-1.5 w-1.5 rounded-full bg-exiqo-glow/80" aria-hidden />
          Active
        </span>
        {tabRelatedPhases.size > 0 && (
          <span className="flex items-center gap-1.5 text-[10px] text-white/30">
            <span className="h-1.5 w-1.5 rounded-full bg-ss-cyan/70" aria-hidden />
            This section
          </span>
        )}
      </div>

      {/* ── Phase detail strip ── */}
      {shownMeta && (
        <motion.div
          key={shownMeta.phase}
          id={detailPanelId}
          className="mt-4 border-t border-white/[0.06] pt-4"
          initial={reduce ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-white/35">
                {CATEGORY_LABELS[shownMeta.category]} &nbsp;·&nbsp; Phase {shownMeta.phase} of 12
              </p>
              <p className="mt-1.5 font-heading text-sm font-semibold text-white">
                {shownMeta.title}
              </p>
              <p className="mt-1 max-w-xl text-[11px] leading-relaxed text-white/55 sm:text-xs">
                {shownMeta.nextHint}
              </p>
            </div>
            <div className="flex shrink-0 flex-col gap-2 sm:items-end">
              <button
                type="button"
                onClick={() => openWorkspace(shownMeta.tabId, shownMeta.fraudshieldTab)}
                className="inline-flex min-h-[44px] w-full items-center justify-center gap-1.5 rounded-xl border border-white/[0.12] bg-white/[0.06] px-4 py-2 text-sm font-medium text-white transition-all duration-300 ease-brand hover:bg-white/[0.10] hover:border-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50 sm:w-auto"
              >
                Open layer
                <ChevronRight className="h-4 w-4 opacity-70" aria-hidden />
              </button>
              {onAdvancePhase && !journeyComplete && shownMeta.phase === phase && (
                <button
                  type="button"
                  onClick={() => { onAdvancePhase(); setDetailPhase(null); }}
                  className="min-h-[36px] px-1 text-[11px] font-medium text-white/40 underline-offset-4 transition hover:text-white/75 hover:underline sm:text-right"
                >
                  Mark layer complete
                </button>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </GlassCard>
  );
}

export const MasteryJourneyRail = memo(MasteryJourneyRailInner);
export default MasteryJourneyRail;
