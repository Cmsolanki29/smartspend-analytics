/**
 * SmartSpend AI Financial Partner Chatbot — World-class interactive
 *
 * Features:
 * - 12ms per-character typewriter effect with blinking cursor
 * - Route deep-link pill buttons (navigate to EMI, Fraud, Transactions, etc.)
 * - Quick-reply chips from AI response
 * - Premium message bubble design (left accent border, avatar, timestamp)
 * - Fade-in animation per bubble
 * - "SmartSpend Partner is typing…" indicator
 * - Circular send button with arrow icon
 * - Glowing focus ring on input
 * - Empty state with 4 starter chips
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../../context/AuthContext";
import { useAppData } from "../../context/AppDataContext";
import { useViewMode } from "../../context/ViewModeContext";
import { getLinkedAccounts, TOKEN_ACCESS_KEY } from "../../services/api";
import { renderMarkdownLite, TypewriterText } from "../common/TypewriterText";

const MONTH_LABELS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const DASHBOARD_MODE_LABELS = {
  merged: "All accounts",
  bank_only: "Bank only",
  credit_card_only: "Card only",
};

// ── Response parser ────────────────────────────────────────────────────────
function parseMessage(raw) {
  const routes = [];
  // supports both ROUTE:{"label":"...","path":"..."} and ROUTE: Label → /path
  const routeJsonRe = /ROUTE:(\{[^\n}]+\})/g;
  const routeTextRe = /ROUTE:\s*([^→\n]+)→\s*(\S+)/g;
  let m;
  while ((m = routeJsonRe.exec(raw)) !== null) {
    try { routes.push(JSON.parse(m[1])); } catch { /* skip malformed */ }
  }
  while ((m = routeTextRe.exec(raw)) !== null) {
    const label = m[1].trim();
    const path = m[2].trim();
    if (!routes.find((r) => r.path === path)) routes.push({ label, path });
  }

  let chips = [];
  const chipsMatch = raw.match(/CHIPS:([^\n]+)/);
  if (chipsMatch) {
    chips = chipsMatch[1].split("|").map((c) => c.trim()).filter(Boolean).slice(0, 4);
  }

  const clean = raw
    .replace(/ROUTE:\{[^\n}]+\}/g, "")
    .replace(/ROUTE:[^\n]+/g, "")
    .replace(/CHIPS:[^\n]+/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  return { clean, routes, chips };
}

// ── Timestamp ─────────────────────────────────────────────────────────────
const fmt = (ts) =>
  new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

// ── User bubble ────────────────────────────────────────────────────────────
function UserBubble({ content, timestamp }) {
  return (
    <div className="flex justify-end mb-3" style={{ animation: "ss-fade-up 0.22s ease-out both" }}>
      <div className="max-w-[80%] flex flex-col items-end gap-0.5">
        <div
          className="rounded-2xl rounded-br-sm px-4 py-2.5 text-sm leading-relaxed text-white"
          style={{ background: "linear-gradient(135deg,#6d28d9,#4f46e5)" }}
        >
          {content}
        </div>
        <span className="text-[10px] text-white/30 pr-1">{fmt(timestamp)}</span>
      </div>
    </div>
  );
}

// ── System notice bubble (identity warning + optional Connect Account button) ──
function SystemNoticeBubble({ content, timestamp, showConnectButton, onConnect }) {
  return (
    <div className="mb-3 flex justify-center" style={{ animation: "ss-fade-up 0.22s ease-out both" }}>
      <div className="max-w-[92%] rounded-xl border border-amber-500/35 bg-amber-500/12 px-4 py-3 text-xs leading-relaxed text-amber-100">
        {content}
        <span className="mt-1 block text-[10px] text-amber-200/50">{fmt(timestamp)}</span>
        {showConnectButton && (
          <button
            type="button"
            onClick={onConnect}
            className="mt-2.5 inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold text-amber-100 transition-all hover:-translate-y-0.5 active:scale-95"
            style={{
              background: "linear-gradient(135deg,rgba(217,119,6,0.30),rgba(245,158,11,0.18))",
              border: "1px solid rgba(245,158,11,0.45)",
              boxShadow: "0 2px 8px rgba(217,119,6,0.2)",
            }}
          >
            Connect Account →
          </button>
        )}
      </div>
    </div>
  );
}

function AiBubble({ content, onChipClick, onNavigateRoute, isStreaming, timestamp }) {
  const { clean, routes, chips } = parseMessage(content);

  return (
    <div className="flex gap-2.5 mb-4 items-start" style={{ animation: "ss-fade-up 0.22s ease-out both" }}>
      {/* AI avatar */}
      <div
        className="shrink-0 mt-0.5 flex items-center justify-center rounded-full text-[11px] font-bold"
        style={{ width: 30, height: 30, background: "linear-gradient(135deg,#6d28d9,#2563eb)", color: "#fff" }}
      >
        AI
      </div>

      <div className="flex-1 min-w-0">
        {/* Bubble */}
        <div
          className="rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed"
          style={{
            background: "rgba(255,255,255,0.04)",
            borderTop: "1px solid rgba(255,255,255,0.07)",
            borderRight: "1px solid rgba(255,255,255,0.07)",
            borderBottom: "1px solid rgba(255,255,255,0.07)",
            borderLeft: "3px solid rgba(139,92,246,0.55)",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {isStreaming ? (
            <TypewriterText key={`tw-${timestamp}`} text={clean} isStreaming={isStreaming} />
          ) : (
            renderMarkdownLite(clean)
          )}
        </div>

        {/* Timestamp */}
        <span className="text-[10px] text-white/28 ml-1 mt-0.5 block">{fmt(timestamp)}</span>

        {/* Route pill buttons */}
        {!isStreaming && routes.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {routes.map((r, i) => (
              <button
                key={i}
                type="button"
                onClick={() => onNavigateRoute?.(r)}
                className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold text-violet-100 transition-all hover:-translate-y-0.5 active:scale-95"
                style={{
                  background: "linear-gradient(135deg,rgba(109,40,217,0.25),rgba(6,182,212,0.15))",
                  border: "1px solid rgba(139,92,246,0.45)",
                  boxShadow: "0 2px 8px rgba(109,40,217,0.2)",
                }}
              >
                {r.label}
                <span aria-hidden>→</span>
              </button>
            ))}
          </div>
        )}

        {/* Quick-reply chips */}
        {!isStreaming && chips.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {chips.map((c, i) => (
              <button
                key={i}
                type="button"
                onClick={() => onChipClick(c)}
                className="rounded-full border border-white/12 bg-white/[0.03] px-3 py-1 text-xs text-white/55 hover:text-white hover:bg-white/[0.07] hover:border-white/22 transition-colors"
              >
                {c} ↗
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Typing indicator ──────────────────────────────────────────────────────
function TypingIndicator() {
  return (
    <div className="flex gap-2.5 mb-3 items-center" style={{ animation: "ss-fade-up 0.22s ease-out both" }}>
      <div
        className="shrink-0 flex items-center justify-center rounded-full text-[11px] font-bold"
        style={{ width: 30, height: 30, background: "linear-gradient(135deg,#6d28d9,#2563eb)", color: "#fff" }}
      >
        AI
      </div>
      <div className="flex items-center gap-2.5">
        <div
          className="flex gap-1 items-center px-3.5 py-2.5 rounded-2xl rounded-tl-sm"
          style={{
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.07)",
            borderLeft: "3px solid rgba(139,92,246,0.55)",
          }}
        >
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-violet-400/80"
              style={{ animation: `ss-blink 1.2s ${i * 0.2}s infinite ease-in-out` }}
            />
          ))}
        </div>
        <span className="text-[11px] text-white/40 italic select-none">SmartSpend Partner is typing…</span>
      </div>
    </div>
  );
}

// ── Starter chips ─────────────────────────────────────────────────────────
const STARTER_CHIPS = [
  "What's my savings rate this month?",
  "Any unusual transactions?",
  "How are my EMIs?",
  "Where am I spending the most?",
];

const FULL_FEATURE_BUTTONS = [
  { id: "spending", label: "💸 Where I Spend Most" },
  { id: "categories", label: "📊 Top Categories" },
  { id: "unusual", label: "⚠️ Unusual Transactions" },
  { id: "trend", label: "📈 Monthly Trend" },
  { id: "savings", label: "💡 Savings Tips" },
];

const LIMITED_FEATURE_BUTTONS = [
  { id: "spending", label: "💸 Quick Spend Summary" },
  { id: "categories", label: "📊 Category Overview" },
];

function featureButtonsForScope(scope) {
  if (scope === "linked_full") return FULL_FEATURE_BUTTONS;
  if (scope === "unlinked_same_bank") return LIMITED_FEATURE_BUTTONS;
  return [];
}

// ── Main component ─────────────────────────────────────────────────────────
/**
 * @param {(route: { path?: string, tab?: string, label?: string }) => void} [onNavigate]
 * @param {number} [month] — TopBar selected month (1–12)
 * @param {number} [year] — TopBar selected year
 * @param {string} [dashboardScope] — merged | bank_only | credit_card_only
 */
export default function SmartSpendChatbot({ onNavigate, month, year, dashboardScope = "merged" }) {
  const { user } = useAuth();
  const { viewMode } = useViewMode();
  const { linkedAccounts, refreshLinkedAccounts } = useAppData();
  const effectiveScope = dashboardScope || viewMode || "merged";
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [llmOnline, setLlmOnline] = useState(true);
  const [uploadBanner, setUploadBanner] = useState(null);
  const [uploadedDocMeta, setUploadedDocMeta] = useState(null);
  const [docContext, setDocContext] = useState(null);
  const [featureButtons, setFeatureButtons] = useState([]);
  const [identityScope, setIdentityScope] = useState(null);
  const bottomRef = useRef(null);
  const fileRef = useRef(null);
  const hasUserMessagedRef = useRef(false);

  const contextMonth = Number(month) || new Date().getMonth() + 1;
  const contextYear = Number(year) || new Date().getFullYear();
  const monthLabel = MONTH_LABELS[contextMonth - 1] || MONTH_LABELS[0];
  const dashboardModeLabel = DASHBOARD_MODE_LABELS[effectiveScope] || effectiveScope;
  const firstName = (user?.name || "").trim().split(/\s+/)[0] || "there";

  const token = () => localStorage.getItem(TOKEN_ACCESS_KEY) || "";
  const authHeaders = () => ({ Authorization: `Bearer ${token()}` });

  // Auto-scroll — only when there are messages; skip on initial mount to avoid
  // scrolling the page down to the chat section before the user has interacted.
  useEffect(() => {
    if (messages.length === 0) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const prevScopeRef = useRef(effectiveScope);
  useEffect(() => {
    if (prevScopeRef.current === effectiveScope) return;
    prevScopeRef.current = effectiveScope;
    setDocContext(null);
    setFeatureButtons([]);
    setUploadedDocMeta(null);
    setIdentityScope(null);
    setUploadBanner(null);
    setMessages((prev) => [
      ...prev,
      {
        id: `sys-mode-${Date.now()}`,
        role: "system",
        content: `Switched to ${dashboardModeLabel} view. How can I help, ${firstName}?`,
        timestamp: Date.now(),
      },
    ]);
  }, [effectiveScope, dashboardModeLabel, firstName]);

  // Init session + linked accounts (system prompt context)
  useEffect(() => {
    let cancelled = false;
    async function init() {
      try {
        if (user?.id) {
          await refreshLinkedAccounts();
          const linked = await getLinkedAccounts(user.id).catch(() => null);
          const sources = linked?.linked_accounts || linked?.sources || [];
          const hasLedger = sources.some((s) => Number(s.transactions_count) > 0);
          if (!cancelled) {
            setIdentityScope(hasLedger ? "linked_full" : "unlinked_foreign");
            setFeatureButtons(featureButtonsForScope(hasLedger ? "linked_full" : ""));
          }
        }
        const res = await fetch("/api/ai/session", { headers: authHeaders() });
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled) return;
        setSessionId(data.session_id);
        setLlmOnline(data.llm?.status !== "offline");
      } catch { /* non-fatal */ }
    }
    init();
    return () => { cancelled = true; };
  }, [user?.id, refreshLinkedAccounts]);

  // Core send / stream
  const doSend = useCallback(
    async (text, sid, { isFirst = false } = {}) => {
      if (!text.trim()) return;
      setLoading(true);

      const aiId = `ai-${Date.now()}`;
      const ts = Date.now();
      const isFirstMessage = isFirst || !hasUserMessagedRef.current;

      setMessages((prev) => [
        ...prev,
        { id: aiId, role: "assistant", content: "", streaming: true, timestamp: ts },
      ]);

      try {
        const ctrl = new AbortController();
        const tid = window.setTimeout(() => ctrl.abort(), 120_000);
        let res;
        try {
          res = await fetch("/api/ai/chat", {
            method: "POST",
            headers: { ...authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({
              message: text,
              session_id: sid || sessionId,
              is_first_message: isFirstMessage,
              dashboard_scope: effectiveScope,
              context_month: contextMonth,
              context_year: contextYear,
              uploaded_doc_metadata: uploadedDocMeta,
            }),
            signal: ctrl.signal,
          });
        } finally {
          window.clearTimeout(tid);
        }

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = "";
        let sawChunk = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let sep;
          while ((sep = buf.indexOf("\n\n")) >= 0) {
            const block = buf.slice(0, sep).trim();
            buf = buf.slice(sep + 2);
            for (const line of block.split("\n").filter((l) => l.startsWith("data: "))) {
              try {
                const evt = JSON.parse(line.slice(6).trim());
                if (evt.chunk) {
                  sawChunk = true;
                  setMessages((prev) =>
                    prev.map((m) => m.id === aiId ? { ...m, content: m.content + evt.chunk } : m)
                  );
                }
                if (evt.done) {
                  setMessages((prev) =>
                    prev.map((m) => m.id === aiId ? { ...m, streaming: false } : m)
                  );
                }
              } catch { /* skip malformed */ }
            }
          }
        }

        setMessages((prev) =>
          prev.map((m) => {
            if (m.id !== aiId) return m;
            const trimmed = (m.content || "").trim();
            if (!trimmed || (!sawChunk && trimmed.length < 2)) {
              return { ...m, content: "I'm having trouble connecting right now. Please try again in a moment.", streaming: false };
            }
            return { ...m, streaming: false };
          })
        );
      } catch {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === aiId
              ? { ...m, content: "Something went wrong with the connection. Please try again.", streaming: false }
              : m
          )
        );
      } finally {
        hasUserMessagedRef.current = true;
        setLoading(false);
      }
    },
    [sessionId, effectiveScope, contextMonth, contextYear, uploadedDocMeta]
  );

  const featureQueries = useCallback(
    (featureId) => {
      const inst = docContext?.institution || uploadedDocMeta?.institution_name || "this statement";
      const map = {
        spending: `Analyze where ${firstName} spends the most in this ${inst} statement`,
        categories: `Break down spending by category for this ${inst} statement`,
        unusual: `Find any unusual or suspicious transactions in this ${inst} statement`,
        trend: `Show monthly spending trend for this ${inst} statement`,
        savings: `Give savings tips based on this ${inst} statement`,
      };
      return map[featureId] || `Summarize this ${inst} statement for ${firstName}`;
    },
    [docContext, uploadedDocMeta, firstName]
  );

  const handleFeatureClick = (featureId) => {
    if (!docContext || loading) return;
    const q = featureQueries(featureId);
    setMessages((prev) => [...prev, { id: `u-feat-${Date.now()}`, role: "user", content: q, timestamp: Date.now() }]);
    void doSend(q, sessionId);
  };

  const handleSend = () => {
    if (!input.trim() || loading) return;
    const text = input.trim();
    setInput("");
    setMessages((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, role: "user", content: text, timestamp: Date.now() },
    ]);
    void doSend(text, sessionId);
  };

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setMessages((prev) => [
      ...prev,
      { id: `u-upload-${Date.now()}`, role: "user", content: `Uploading ${file.name}…`, timestamp: Date.now() },
    ]);
    setUploadBanner({ state: "uploading", name: file.name });
    const form = new FormData();
    form.append("file", file);
    if (sessionId) form.append("session_id", sessionId);
    try {
      const res = await fetch("/api/ai/upload", { method: "POST", headers: authHeaders(), body: form });
      if (!res.ok) throw new Error(`Upload ${res.status}`);
      const result = await res.json();
      setUploadBanner({ state: "done", ...result });
      const inst =
        result.institution ||
        result.doc_info?.institution_name ||
        result.uploaded_doc_metadata?.institution_name ||
        "your bank";
      const scope = result.identity_scope || result.identity_scope_detail?.scope;
      const limited = scope === "unlinked_same_bank";
      if (result.doc_info || result.uploaded_doc_metadata) {
        setUploadedDocMeta({
          ...(result.uploaded_doc_metadata || {}),
          ...(result.doc_info || {}),
          identity_scope: scope,
          identity_reason: result.reason,
        });
      }
      setDocContext({ institution: inst, limited, file: file.name });
      setFeatureButtons(featureButtonsForScope(scope));
      setIdentityScope(scope || null);

      if (scope === "linked_full") {
        setMessages((prev) => [
          ...prev,
          {
            id: `ai-doc-${Date.now()}`,
            role: "assistant",
            content: `Hey ${firstName}! Here's your ${inst} statement — ${result.transaction_count || 0} transactions parsed. Tap a button below or ask anything.`,
            streaming: false,
            timestamp: Date.now(),
          },
        ]);
      } else if (scope === "unlinked_same_bank") {
        setMessages((prev) => [
          ...prev,
          {
            id: `sys-${Date.now()}`,
            role: "system",
            content:
              result.warning_message ||
              `Hey ${firstName}, this looks like your ${inst} statement, but it isn't linked to SmartSpend yet. Link it in Settings for full analysis.`,
            identity_scope: scope,
            timestamp: Date.now(),
          },
        ]);
      } else if (result.warning_message) {
        setMessages((prev) => [
          ...prev,
          {
            id: `sys-${Date.now()}`,
            role: "system",
            content:
              result.warning_message ||
              `Hey ${firstName}, this statement appears to belong to a different person. I can't analyze someone else's financial data.`,
            identity_scope: scope,
            timestamp: Date.now(),
          },
        ]);
        setFeatureButtons([]);
      }
    } catch {
      setUploadBanner({ state: "error" });
      setMessages((prev) => [
        ...prev,
        { id: `ai-upload-err-${Date.now()}`, role: "assistant", content: "Upload failed. Only PDF, CSV, or TXT files are supported.", streaming: false, timestamp: Date.now() },
      ]);
    }
  };

  const handleChipClick = (q) => {
    if (loading) return;
    setMessages((prev) => [...prev, { id: `u-chip-${Date.now()}`, role: "user", content: q, timestamp: Date.now() }]);
    void doSend(q, sessionId);
  };

  const handleNavigateRoute = typeof onNavigate === "function" ? onNavigate : undefined;

  return (
    <div
      className="flex flex-col rounded-2xl border border-white/[0.08] overflow-hidden"
      style={{ height: 540, background: "var(--color-bg-primary, #0d0d1a)" }}
    >
      {/* ── Header ── */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b border-white/[0.08] shrink-0"
        style={{ background: "rgba(255,255,255,0.025)" }}
      >
        <div className="flex items-center gap-2.5">
          <div
            className="flex items-center justify-center rounded-full text-xs font-bold shrink-0"
            style={{ width: 36, height: 36, background: "linear-gradient(135deg,#6d28d9,#2563eb)", color: "#fff" }}
          >
            AI
          </div>
          <div>
            <p className="text-sm font-semibold text-white">SmartSpend Partner</p>
            <p className="flex items-center gap-1.5 text-[11px] text-white/50">
              <span
                className="inline-block h-1.5 w-1.5 rounded-full shrink-0"
                style={{ background: llmOnline ? "#10b981" : "#f87171" }}
              />
              <span>{llmOnline ? "Online" : "Unavailable"}</span>
              <span className="text-white/30">·</span>
              <span>Grounded in your data</span>
            </p>
          </div>
        </div>
        {messages.length > 0 && sessionId && (
          <button
            type="button"
            className="rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-white/40 hover:text-white/70 hover:border-white/20 transition-colors"
            onClick={async () => {
              try { await fetch(`/api/ai/session/${sessionId}`, { method: "DELETE", headers: authHeaders() }); } catch { /* ignore */ }
              setMessages([]);
              setUploadedDocMeta(null);
              setDocContext(null);
              setFeatureButtons([]);
              setIdentityScope(null);
              hasUserMessagedRef.current = false;
              try {
                const res = await fetch("/api/ai/session", { headers: authHeaders() });
                const data = await res.json();
                setSessionId(data.session_id);
                setLlmOnline(data.llm?.status !== "offline");
              } catch { /* ignore */ }
            }}
          >
            Clear Chat
          </button>
        )}
      </div>
      <div
        style={{
          fontSize: 11,
          color: "var(--color-text-tertiary, rgba(255,255,255,0.35))",
          textAlign: "center",
          padding: "4px 0",
          borderBottom: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        Answering for {monthLabel} {contextYear} · {dashboardModeLabel}
      </div>

      {/* ── Messages ── */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {/* Empty state */}
        {messages.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center h-full pb-4 text-center select-none">
            <div
              className="flex items-center justify-center rounded-full mb-3"
              style={{ width: 56, height: 56, background: "linear-gradient(135deg,#6d28d9,#2563eb)", boxShadow: "0 0 24px rgba(109,40,217,0.4)" }}
            >
              <svg width="26" height="26" fill="none" viewBox="0 0 24 24" stroke="white" strokeWidth="1.8">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636-.707.707M21 12h-1M4 12H3m3.343-5.657-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
            <h3 className="text-sm font-bold text-white/90 mb-1">Ask me anything about your finances</h3>
            <p className="text-xs text-white/40 max-w-[260px] leading-relaxed mb-5">
              I can help with spending analysis, EMI details, savings goals, and more.
            </p>
            <div className="flex flex-wrap gap-2 justify-center max-w-sm">
              {STARTER_CHIPS.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => {
                    setMessages([{ id: `u-${Date.now()}`, role: "user", content: q, timestamp: Date.now() }]);
                    void doSend(q, sessionId);
                  }}
                  className="rounded-full border border-violet-500/35 bg-violet-500/10 px-3.5 py-1.5 text-xs text-violet-200 hover:bg-violet-500/20 hover:border-violet-500/60 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => {
          if (msg.role === "user") {
            return <UserBubble key={msg.id} content={msg.content} timestamp={msg.timestamp ?? Date.now()} />;
          }
          if (msg.role === "system") {
            const msgScope = msg.identity_scope || identityScope;
            const isUnlinked = msgScope === "unlinked_foreign" || msgScope === "unlinked_same_bank";
            return (
              <SystemNoticeBubble
                key={msg.id}
                content={msg.content}
                timestamp={msg.timestamp ?? Date.now()}
                showConnectButton={isUnlinked}
                onConnect={() => onNavigate?.({ tab: "settings", path: "/settings" })}
              />
            );
          }
          return (
            <AiBubble
              key={msg.id}
              content={msg.content}
              isStreaming={!!msg.streaming}
              onChipClick={handleChipClick}
              onNavigateRoute={handleNavigateRoute}
              timestamp={msg.timestamp ?? Date.now()}
            />
          );
        })}
        {loading && messages[messages.length - 1]?.role !== "assistant" && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* ── Upload banners ── */}
      {uploadBanner?.state === "done" && (
        <div className="mx-4 mb-2 shrink-0 flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
          <span className="text-emerald-400">✓</span>
          <span>
            <strong>{uploadBanner.institution || "Document"}</strong> parsed —{" "}
            {uploadBanner.transaction_count} transactions
            {uploadBanner.date_range ? ` · ${uploadBanner.date_range}` : ""}
          </span>
          <button type="button" className="ml-auto text-emerald-400/60 hover:text-emerald-400" onClick={() => setUploadBanner(null)}>×</button>
        </div>
      )}
      {uploadBanner?.state === "uploading" && (
        <div className="mx-4 mb-2 shrink-0 flex items-center gap-2 rounded-xl border border-violet-500/25 bg-violet-500/10 px-3 py-2 text-xs text-violet-200">
          <span className="animate-spin">⏳</span> Parsing {uploadBanner.name}…
        </div>
      )}
      {uploadBanner?.state === "error" && (
        <div className="mx-4 mb-2 shrink-0 flex items-center gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          <span>⚠</span> Upload failed.
          <button type="button" className="ml-auto text-rose-400/60 hover:text-rose-400" onClick={() => setUploadBanner(null)}>×</button>
        </div>
      )}

      {(featureButtons.length > 0 ||
        featureButtonsForScope(
          linkedAccounts.some((s) => Number(s.transactions_count) > 0) ? "linked_full" : ""
        ).length > 0) && (
        <div className="mx-4 mb-2 flex shrink-0 flex-wrap gap-2 border-t border-white/[0.06] pt-3">
          {(featureButtons.length
            ? featureButtons
            : featureButtonsForScope(
                linkedAccounts.some((s) => Number(s.transactions_count) > 0) ? "linked_full" : ""
              )
          ).map((btn) => (
            <button
              key={btn.id}
              type="button"
              disabled={loading}
              onClick={() => handleFeatureClick(btn.id)}
              className="rounded-full border border-violet-500/35 bg-violet-500/10 px-3 py-1.5 text-xs text-violet-200 hover:bg-violet-500/20 disabled:opacity-50"
            >
              {btn.label}
            </button>
          ))}
        </div>
      )}

      {/* ── Input bar ── */}
      <div className="flex items-center gap-2 px-4 py-3 border-t border-white/[0.08] shrink-0">
        {/* Upload (+) button */}
        <button
          type="button"
          title="Upload bank statement, EMI PDF, or CSV"
          onClick={() => fileRef.current?.click()}
          className="shrink-0 flex items-center justify-center rounded-full border border-white/15 bg-white/[0.04] hover:bg-white/[0.09] transition-colors"
          style={{ width: 38, height: 38 }}
        >
          <svg width="17" height="17" fill="none" viewBox="0 0 24 24" stroke="rgba(255,255,255,0.5)" strokeWidth="2.2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
        </button>
        <input ref={fileRef} type="file" accept=".pdf,.csv,.txt" className="hidden" onChange={handleFile} />

        {/* Text input */}
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
          placeholder={loading ? "SmartSpend Partner is responding…" : "Ask anything — EMIs, spending, savings…"}
          disabled={loading}
          className="flex-1 rounded-full border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm text-white placeholder:text-white/30 focus:outline-none disabled:opacity-60 transition-all"
          onFocus={(e) => {
            e.target.style.borderColor = "rgba(139,92,246,0.55)";
            e.target.style.boxShadow = "0 0 0 3px rgba(139,92,246,0.14)";
          }}
          onBlur={(e) => {
            e.target.style.borderColor = "";
            e.target.style.boxShadow = "";
          }}
        />

        {/* Send button — circular with arrow */}
        <button
          type="button"
          onClick={handleSend}
          disabled={loading || !input.trim()}
          className="shrink-0 flex items-center justify-center rounded-full text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed hover:scale-105 active:scale-95"
          style={{ width: 38, height: 38, background: "linear-gradient(135deg,#6d28d9,#2563eb)", boxShadow: "0 2px 10px rgba(109,40,217,0.4)" }}
        >
          <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="white" strokeWidth="2.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14m-7-7 7 7-7 7" />
          </svg>
        </button>
      </div>

      {/* ── Keyframes ── */}
      <style>{`
        @keyframes ss-blink {
          0%,100% { opacity:0.15; transform:scale(0.8); }
          50% { opacity:1; transform:scale(1); }
        }
        @keyframes ss-cursor-blink {
          0%,100% { opacity:1; }
          50% { opacity:0; }
        }
        @keyframes ss-fade-up {
          from { opacity:0; transform:translateY(6px); }
          to { opacity:1; transform:translateY(0); }
        }
      `}</style>
    </div>
  );
}
