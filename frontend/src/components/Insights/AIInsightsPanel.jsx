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
import { getInsights } from "../../services/api";
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
          <p className="text-xs font-semibold uppercase tracking-wide text-exiqo-glow/55">{title}</p>
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
                    className="mt-2 space-y-1 overflow-hidden border-l-2 border-cyan-400/40 pl-3 text-xs text-exiqo-glow/80"
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
  const [state, setState] = useState({ data: null, loading: true, error: "", refreshedAt: null });
  const [typedDone, setTypedDone] = useState(false);
  const [whyOpen, setWhyOpen] = useState(false);

  const fetchInsights = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: "" }));
    try {
      const data = await getInsights(userId, month, year);
      setState({ data, loading: false, error: "", refreshedAt: new Date() });
      setTypedDone(false);
      setWhyOpen(false);
    } catch (error) {
      setState((prev) => ({
        data: prev.data,
        loading: false,
        error: error.message || "AI insights temporarily unavailable",
        refreshedAt: prev.refreshedAt,
      }));
    }
  }, [userId, month, year]);

  useEffect(() => {
    fetchInsights();
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
        <p className="mb-2 text-xs text-exiqo-glow/60">AI is analysing your finances…</p>
        <SkeletonCard lines={5} height={220} />
      </div>
    );
  }

  if (!state.data) {
    return <ErrorCard message={state.error || "Unable to load insights."} onRetry={fetchInsights} />;
  }

  if (presentation === "chat") {
    return (
      <div className="space-y-3">
        {state.error ? (
          <div className="mb-2">
            <ErrorCard message={state.error} onRetry={fetchInsights} />
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
          <p className="text-[11px] text-exiqo-glow/50">Last updated: {updatedAgo}</p>
          <button
            type="button"
            onClick={fetchInsights}
            className="inline-flex min-h-[48px] items-center gap-2 rounded-xl border border-white/10 bg-white/[0.05] px-3 py-2 text-xs font-semibold text-white transition hover:bg-white/[0.1] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 md:min-h-0"
          >
            <RefreshCcw className="h-3.5 w-3.5" aria-hidden />
            Refresh
          </button>
        </div>
      </div>
    );
  }

  return (
    <section className="glass-card ai-panel border-white/[0.08]">
      <div className="panel-head">
        <h3>AI Insights</h3>
        <button
          type="button"
          className="ghost-btn inline-flex min-h-[48px] items-center gap-2 focus-visible:ring-2 focus-visible:ring-cyan-400/60 md:min-h-0"
          onClick={fetchInsights}
        >
          <RefreshCcw size={14} aria-hidden /> Regenerate
        </button>
      </div>

      {state.error ? (
        <div className="mb-3">
          <ErrorCard message={state.error} onRetry={fetchInsights} />
        </div>
      ) : null}
      <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold ${verdict.cls}`}>
        <VerdictIcon className="h-4 w-4" aria-hidden />
        {verdict.label}
      </div>
      <p className="insight-summary mt-3 text-sm text-white/90">{insight.summary || "AI insights temporarily unavailable"}</p>

      <div className="insight-section mt-4">
        <h4 className="flex items-center gap-2 text-sm font-semibold text-white">
          <ListChecks className="h-4 w-4 text-exiqo-glow" aria-hidden />
          Key insights
        </h4>
        <ul className="mt-2 space-y-1 text-sm text-exiqo-glow/80">
          {keyInsights.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      </div>

      {warnings.length > 0 ? (
        <div className="insight-section warnings mt-4">
          <h4 className="flex items-center gap-2 text-sm font-semibold text-rose-200">
            <AlertTriangle className="h-4 w-4" aria-hidden />
            Warnings
          </h4>
          <ul className="mt-2 space-y-1 text-sm text-exiqo-glow/80">
            {warnings.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="insight-section mt-4">
        <h4 className="flex items-center gap-2 text-sm font-semibold text-white">
          <Lightbulb className="h-4 w-4 text-amber-200" aria-hidden />
          Recommendations
        </h4>
        <ul className="mt-2 space-y-1 text-sm text-exiqo-glow/80">
          {recommendations.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      </div>

      {positives.length > 0 ? (
        <div className="insight-section mt-4">
          <h4 className="flex items-center gap-2 text-sm font-semibold text-white">
            <ThumbsUp className="h-4 w-4 text-emerald-300" aria-hidden />
            Positive highlights
          </h4>
          <ul className="mt-2 space-y-1 text-sm text-exiqo-glow/80">
            {positives.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="muted-text mt-3 text-xs text-exiqo-glow/50">Last updated: {updatedAgo}</p>
    </section>
  );
};

export default AIInsightsPanel;
