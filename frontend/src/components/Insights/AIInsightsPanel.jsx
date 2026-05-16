import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Lightbulb,
  ListChecks,
  RefreshCcw,
  Sparkles,
  ThumbsUp,
} from "lucide-react";
import { fetchInsightsSse } from "../../services/api";
import { ErrorCard } from "../common/ErrorCard";
import { GlassCard } from "../intro/GlassCard";
import { SkeletonCard } from "../common/SkeletonCard";

const verdictMeta = {
  GOOD: { label: "Great financial health", Icon: ThumbsUp, cls: "border-emerald-500/35 bg-emerald-500/10 text-emerald-200" },
  AVERAGE: { label: "Room for improvement", Icon: Lightbulb, cls: "border-amber-500/35 bg-amber-500/10 text-amber-100" },
  NEEDS_IMPROVEMENT: { label: "Take action", Icon: AlertTriangle, cls: "border-orange-500/35 bg-orange-500/10 text-orange-100" },
  CRITICAL: { label: "Immediate attention", Icon: AlertTriangle, cls: "border-rose-500/40 bg-rose-500/10 text-rose-100" },
};

function Typewriter({ text, active, onDone }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(reduce ? String(text || "") : "");

  useEffect(() => {
    if (!active || reduce) {
      setShown(String(text || ""));
      onDone?.();
      return;
    }
    const full = String(text || "");
    setShown("");
    let i = 0;
    const id = window.setInterval(() => {
      i += 1;
      setShown(full.slice(0, i));
      if (i >= full.length) {
        window.clearInterval(id);
        onDone?.();
      }
    }, 22);
    return () => window.clearInterval(id);
  }, [text, active, reduce, onDone]);

  return <span>{shown}</span>;
}

function ChatBubble({ title, body, icon: Icon, tone = "neutral", expanded, onToggleWhy, whyLines }) {
  return (
    <GlassCard padding="sm" surface="panel" className={`border-white/[0.08] ${tone === "warn" ? "border-rose-500/25" : ""}`}>
      <div className="flex gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/[0.06] text-exiqo-glow">
          {Icon ? <Icon className="h-5 w-5" aria-hidden /> : <Sparkles className="h-5 w-5" aria-hidden />}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{title}</p>
          <div className="mt-1 text-sm leading-relaxed text-white/90">{body}</div>
          {whyLines?.length ? (
            <div className="mt-2">
              <button
                type="button"
                onClick={onToggleWhy}
                className="inline-flex min-h-[48px] items-center gap-1 text-xs font-semibold text-cyan-300 transition hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 md:min-h-0"
              >
                Why?
                {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              </button>
              <AnimatePresence initial={false}>
                {expanded ? (
                  <motion.ul
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                    className="mt-2 space-y-1 overflow-hidden border-l-2 border-cyan-400/40 pl-3 text-xs text-gray-300"
                  >
                    {whyLines.map((line, i) => (
                      <li key={i}>{line}</li>
                    ))}
                  </motion.ul>
                ) : null}
              </AnimatePresence>
            </div>
          ) : null}
        </div>
      </div>
    </GlassCard>
  );
}

const AIInsightsPanel = ({ userId, month, year, presentation = "default" }) => {
  const reduce = useReducedMotion();
  const [state, setState] = useState({
    data: null,
    loading: true,
    error: "",
    refreshedAt: null,
    streamingPulse: false,
  });
  const [typedDone, setTypedDone] = useState(false);
  const [whyOpen, setWhyOpen] = useState(false);

  const fetchInsights = useCallback(async () => {
    setState((prev) => ({
      ...prev,
      loading: true,
      error: "",
      streamingPulse: false,
    }));
    const onEvent = (evt) => {
      if (evt && (evt.pulse === true || evt.status === "analyzing")) {
        setState((prev) => ({ ...prev, streamingPulse: true }));
      }
    };
    const runOnce = async () =>
      fetchInsightsSse(userId, month, year, (e) => {
        onEvent(e);
      });

    try {
      const data = await runOnce();
      setState({
        data,
        loading: false,
        error: "",
        refreshedAt: new Date(),
        streamingPulse: false,
      });
      setTypedDone(false);
      setWhyOpen(false);
    } catch {
      try {
        await new Promise((r) => setTimeout(r, 8000));
        const data = await runOnce();
        setState({
          data,
          loading: false,
          error: "",
          refreshedAt: new Date(),
          streamingPulse: false,
        });
        setTypedDone(false);
        setWhyOpen(false);
      } catch {
        setState((prev) => ({
          data: prev.data,
          loading: false,
          error: "Insights are taking longer than usual.",
          refreshedAt: prev.refreshedAt,
          streamingPulse: false,
        }));
      }
    }
  }, [userId, month, year]);

  useEffect(() => {
    fetchInsights();
  }, [fetchInsights]);

  useEffect(() => {
    const handler = () => fetchInsights();
    window.addEventListener("dashboardModeChanged", handler);
    return () => window.removeEventListener("dashboardModeChanged", handler);
  }, [fetchInsights]);

  const insight = state.data?.insights || {};
  const verdict = verdictMeta[insight.spending_verdict] || verdictMeta.AVERAGE;
  const VerdictIcon = verdict.Icon;

  const updatedAgo = useMemo(() => {
    if (!state.refreshedAt) return "just now";
    const mins = Math.max(1, Math.round((Date.now() - state.refreshedAt.getTime()) / 60000));
    return `${mins} min ago`;
  }, [state.refreshedAt]);

  const keyInsights = Array.isArray(insight.key_insights) ? insight.key_insights : [];
  const warnings = Array.isArray(insight.warnings) ? insight.warnings : [];
  const recommendations = Array.isArray(insight.recommendations) ? insight.recommendations : [];
  const positives = Array.isArray(insight.positive_highlights) ? insight.positive_highlights : [];

  if (state.loading) {
    return (
      <div>
        <div className="mb-2 flex items-center gap-2 text-xs text-gray-400">
          <span
            className={`inline-block h-2 w-2 rounded-full bg-violet-400 ${state.streamingPulse ? "animate-pulse" : ""}`}
            aria-hidden
          />
          <span className={state.streamingPulse ? "animate-pulse" : ""}>Analyzing your transactions…</span>
        </div>
        <SkeletonCard lines={5} height={220} />
      </div>
    );
  }

  if (!state.data) {
    return (
      <ErrorCard
        variant="warning"
        message={state.error || "Unable to load insights."}
        onRetry={fetchInsights}
      />
    );
  }

  if (presentation === "chat") {
    return (
      <div className="space-y-3">
        {state.error ? (
          <div className="mb-2">
            <ErrorCard variant="warning" message={state.error} onRetry={fetchInsights} />
          </div>
        ) : null}
        <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold ${verdict.cls}`}>
          <VerdictIcon className="h-3.5 w-3.5" aria-hidden />
          {verdict.label}
        </div>
        <ChatBubble
          title="Summary"
          body={
            <Typewriter text={insight.summary || "AI insights temporarily unavailable."} active={!typedDone} onDone={() => setTypedDone(true)} />
          }
          icon={Sparkles}
          whyLines={keyInsights.length ? keyInsights : null}
          expanded={whyOpen}
          onToggleWhy={() => setWhyOpen((v) => !v)}
        />
        {warnings.length ? (
          <motion.div initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.15 }}>
            <ChatBubble title="Warnings" body={warnings.join(" · ")} icon={AlertTriangle} tone="warn" />
          </motion.div>
        ) : null}
        {recommendations.slice(0, 3).map((item, i) => (
          <motion.div
            key={i}
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08 * (i + 1), duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            <ChatBubble title="Recommendation" body={item} icon={ListChecks} />
          </motion.div>
        ))}
        {positives.slice(0, 2).map((item, i) => (
          <motion.div key={`p-${i}`} initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 + i * 0.06 }}>
            <ChatBubble title="Highlight" body={item} icon={ThumbsUp} />
          </motion.div>
        ))}
        <div className="flex items-center justify-between pt-1">
          <p className="text-[11px] text-gray-500">Last updated: {updatedAgo}</p>
          <button
            type="button"
            onClick={fetchInsights}
            className="inline-flex min-h-[48px] items-center gap-2 rounded-xl border border-white/10 bg-white/[0.05] px-3 py-2 text-xs font-semibold text-white transition hover:bg-white/[0.1] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 md:min-h-0"
          >
            <RefreshCcw className="h-3.5 w-3.5" aria-hidden />
            Refresh Insights
          </button>
        </div>
      </div>
    );
  }

  return (
    <GlassCard padding="md" surface="panel" className="border-white/[0.08]">
      {/* ── Header ── */}
      <div className="mb-4 flex items-start justify-between gap-2">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-gray-500">AI Insights</p>
          <h3 className="mt-0.5 font-heading text-base font-semibold text-white">Your Financial Overview</h3>
        </div>
        <button
          type="button"
          onClick={fetchInsights}
          disabled={state.loading}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-semibold text-white/70 transition hover:bg-white/[0.08] hover:text-white disabled:opacity-50"
        >
          <RefreshCcw
            className={`h-3 w-3 ${state.loading ? "animate-spin" : ""}`}
            aria-hidden
          />
          Refresh
        </button>
      </div>

      {state.error ? (
        <div className="mb-3">
          <ErrorCard variant="warning" message={state.error} onRetry={fetchInsights} />
        </div>
      ) : null}

      {/* ── Verdict pill ── */}
      <div className={`mb-4 inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold ${verdict.cls}`}>
        <VerdictIcon className="h-3.5 w-3.5" aria-hidden />
        {verdict.label}
      </div>

      {/* ── Summary — highlighted AI box ── */}
      <div
        className="mb-4 rounded-xl px-4 py-3 text-sm leading-relaxed text-white/90"
        style={{
          background: "rgba(109,40,217,0.09)",
          border: "1px solid rgba(139,92,246,0.2)",
        }}
      >
        {insight.summary || "AI insights temporarily unavailable."}
      </div>

      {/* ── Key insights ── */}
      {keyInsights.length > 0 && (
        <div className="mb-4">
          <div className="mb-2 flex items-center gap-2 border-l-2 border-violet-500/60 pl-2.5">
            <ListChecks className="h-3.5 w-3.5 text-violet-400" aria-hidden />
            <span className="text-xs font-bold uppercase tracking-[0.1em] text-gray-500">Key Insights</span>
          </div>
          <ul className="space-y-1">
            {keyInsights.map((item, i) => (
              <motion.li
                key={i}
                className="flex items-start gap-2 rounded-lg px-2 py-1 text-sm text-white/80 hover:bg-white/[0.03] transition-colors cursor-default"
                initial={reduce ? false : { opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.05 * i, duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
              >
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-violet-400/80" aria-hidden />
                {item}
              </motion.li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Warnings ── */}
      {warnings.length > 0 && (
        <div className="mb-4">
          <div className="mb-2 flex items-center gap-2 border-l-2 border-rose-500/60 pl-2.5">
            <AlertTriangle className="h-3.5 w-3.5 text-rose-400" aria-hidden />
            <span className="text-xs font-bold uppercase tracking-[0.1em] text-rose-300">Warnings</span>
          </div>
          <ul className="space-y-1">
            {warnings.map((item, i) => (
              <motion.li
                key={i}
                className="flex items-start gap-2 rounded-lg px-2 py-1 text-sm text-white/80 hover:bg-rose-500/[0.05] transition-colors cursor-default"
                initial={reduce ? false : { opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.05 * i, duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
              >
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-rose-400/80" aria-hidden />
                {item}
              </motion.li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Recommendations ── */}
      {recommendations.length > 0 && (
        <div className="mb-4">
          <div className="mb-2 flex items-center gap-2 border-l-2 border-amber-400/60 pl-2.5">
            <Lightbulb className="h-3.5 w-3.5 text-amber-400" aria-hidden />
            <span className="text-xs font-bold uppercase tracking-[0.1em] text-amber-300">Recommendations</span>
          </div>
          <ul className="space-y-1">
            {recommendations.map((item, i) => (
              <motion.li
                key={i}
                className="flex items-start gap-2 rounded-lg px-2 py-1 text-sm text-white/80 hover:bg-amber-500/[0.05] transition-colors cursor-default"
                initial={reduce ? false : { opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.05 * i, duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
              >
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400/80" aria-hidden />
                {item}
              </motion.li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Positives ── */}
      {positives.length > 0 && (
        <div className="mb-4">
          <div className="mb-2 flex items-center gap-2 border-l-2 border-emerald-500/60 pl-2.5">
            <ThumbsUp className="h-3.5 w-3.5 text-emerald-400" aria-hidden />
            <span className="text-xs font-bold uppercase tracking-[0.1em] text-emerald-300">Positive Highlights</span>
          </div>
          <ul className="space-y-1">
            {positives.map((item, i) => (
              <motion.li
                key={i}
                className="flex items-start gap-2 rounded-lg px-2 py-1 text-sm text-white/80 hover:bg-emerald-500/[0.05] transition-colors cursor-default"
                initial={reduce ? false : { opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.05 * i, duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
              >
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400/80" aria-hidden />
                {item}
              </motion.li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Footer ── */}
      <div className="mt-2 border-t border-white/[0.06] pt-3">
        <p className="text-[11px] text-white/35">Last updated: {updatedAgo}</p>
      </div>
    </GlassCard>
  );
};

export default AIInsightsPanel;
