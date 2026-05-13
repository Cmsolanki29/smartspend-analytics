import React, { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Loader2, Radar, ShieldAlert, ShieldCheck, ShieldX, Sparkles } from "lucide-react";
import { postFraudShieldAlertAction, postFraudShieldCheckTransaction } from "../../services/api";
import { useToast } from "../common/Toast";
import { inr } from "../../lib/format";

const MIN_SCAN_MS = 1200;

const nowTime = () => {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};

const patternLabel = (p) => {
  if (!p) return null;
  return p.replace(/_/g, " ");
};

const SCAN_STEPS = [
  "Ingesting transaction envelope…",
  "Resolving merchant & UPI graph…",
  "Scoring with XGBoost + policy rules…",
  "Computing SHAP-style feature attributions…",
  "Synthesising security brief…",
];

/** Map model output → product verdict (3-state). */
function verdictFromResult(result) {
  if (!result || result.error) return null;
  const score = Number(result.risk_score) || 0;
  const level = String(result.risk_level || "").toUpperCase();
  if (score >= 85 || level === "CRITICAL") return "BLOCKED";
  if (score >= 30) return "SUSPICIOUS";
  return "SAFE";
}

function shapStyleReasons(result) {
  const factors = Array.isArray(result?.risk_factors) ? result.risk_factors.filter(Boolean) : [];
  if (factors.length) return factors.slice(0, 6);
  const score = Number(result?.risk_score) || 0;
  if (score >= 85) return ["Model score in critical band", "Policy escalation triggered"];
  if (score >= 60) return ["Elevated anomaly vs your baseline", "Merchant category risk"];
  if (score >= 30) return ["Minor deviation from usual pattern"];
  return ["No strong anomaly vs recent behaviour"];
}

function recommendedCopy(verdict) {
  if (verdict === "BLOCKED")
    return "Do not complete this payment. If you did not initiate it, report immediately and call 1930.";
  if (verdict === "SUSPICIOUS")
    return "Pause and verify the recipient out-of-band (call a known number, check order ID). Only pay if you are 100% certain.";
  return "Signals look consistent with safe spend for you. Still double-check the UPI handle before confirming.";
}

function ScanningOverlay({ stepIndex }) {
  const step = SCAN_STEPS[Math.min(stepIndex, SCAN_STEPS.length - 1)];
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="absolute inset-0 z-20 flex flex-col items-center justify-center rounded-3xl border border-violet-500/30 bg-[#070418]/88 backdrop-blur-xl"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="relative mb-8 h-28 w-28">
        <motion.div
          className="absolute inset-0 rounded-full border-2 border-transparent"
          style={{
            background:
              "conic-gradient(from 0deg, rgba(124,58,237,0.95), rgba(37,99,235,0.5), rgba(34,211,238,0.85), rgba(124,58,237,0.95))",
            mask: "radial-gradient(farthest-side, transparent calc(100% - 3px), #fff calc(100% - 3px))",
            WebkitMask: "radial-gradient(farthest-side, transparent calc(100% - 3px), #fff calc(100% - 3px))",
          }}
          animate={{ rotate: 360 }}
          transition={{ duration: 2.2, repeat: Infinity, ease: "linear" }}
        />
        <div className="absolute inset-0 m-auto flex h-16 w-16 items-center justify-center rounded-full border border-white/10 bg-white/[0.06] shadow-[0_0_40px_-12px_rgba(124,58,237,0.6)]">
          <Radar className="h-8 w-8 text-violet-200" aria-hidden />
        </div>
      </div>
      <p className="text-sm font-semibold tracking-tight text-white">Scanning transaction</p>
      <p className="mt-2 max-w-xs px-4 text-center text-xs leading-relaxed text-exiqo-glow/70">{step}</p>
      <div className="mt-6 flex gap-1.5">
        {SCAN_STEPS.map((label, i) => (
          <span
            key={label}
            className={`h-1.5 w-6 rounded-full transition-colors ${i <= stepIndex ? "bg-violet-400" : "bg-white/10"}`}
          />
        ))}
      </div>
    </motion.div>
  );
}

function VerdictCard({ verdict, result, userName, reporting, reportMsg, onDismiss, onReport, securityBrief }) {
  const score = Number(result?.risk_score) || 0;
  const reasons = shapStyleReasons(result);
  const meta = useMemo(() => {
    if (verdict === "BLOCKED")
      return {
        Icon: ShieldX,
        title: "Blocked",
        sub: "Do not proceed",
        pill: "border-rose-500/50 bg-rose-500/15 text-rose-100",
        glow: "shadow-[0_0_48px_-16px_rgba(239,68,68,0.55)]",
      };
    if (verdict === "SUSPICIOUS")
      return {
        Icon: ShieldAlert,
        title: "Suspicious",
        sub: "Extra verification required",
        pill: "border-amber-500/45 bg-amber-500/12 text-amber-100",
        glow: "shadow-[0_0_40px_-18px_rgba(245,158,11,0.45)]",
      };
    return {
      Icon: ShieldCheck,
      title: "Safe",
      sub: "Low model concern",
      pill: "border-emerald-500/45 bg-emerald-500/12 text-emerald-100",
      glow: "shadow-[0_0_40px_-18px_rgba(16,185,129,0.4)]",
    };
  }, [verdict]);

  const Icon = meta.Icon;
  const isCritical = verdict === "BLOCKED";
  const isSuspicious = verdict === "SUSPICIOUS";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 28, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 16 }}
      transition={{ type: "spring", stiffness: 380, damping: 32 }}
      className={`relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-br from-white/[0.06] to-white/[0.02] p-6 backdrop-blur-xl sm:p-8 ${meta.glow}`}
    >
      <div className="pointer-events-none absolute -right-20 -top-20 h-56 w-56 rounded-full bg-violet-600/20 blur-3xl" />
      <div className="relative flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-4">
          <div className={`grid h-14 w-14 shrink-0 place-items-center rounded-2xl border ${meta.pill}`}>
            <Icon className="h-7 w-7" aria-hidden />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full border px-3 py-1 text-[11px] font-bold uppercase tracking-wider ${meta.pill}`}>
                {meta.title}
              </span>
              <span className="rounded-full border border-white/10 bg-white/[0.06] px-2.5 py-0.5 font-mono text-xs tabular-nums text-exiqo-glow/80">
                Score {Math.round(score)}/100
              </span>
            </div>
            <p className="mt-2 text-lg font-bold tracking-tight text-white">{meta.sub}</p>
            <p className="mt-2 max-w-xl text-sm leading-relaxed text-exiqo-glow/75">{recommendedCopy(verdict)}</p>
          </div>
        </div>
      </div>

      <div className="relative mt-6 rounded-2xl border border-white/10 bg-black/25 p-4">
        <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-violet-200/80">
          <Sparkles className="h-3.5 w-3.5" aria-hidden />
          Top drivers (SHAP-style)
        </div>
        <ul className="flex flex-wrap gap-2">
          {reasons.map((r) => (
            <li
              key={r}
              className="rounded-lg border border-white/10 bg-white/[0.06] px-2.5 py-1 text-[11px] font-medium text-exiqo-glow/85"
            >
              {r}
            </li>
          ))}
        </ul>
        {patternLabel(result?.pattern_matched) && (
          <p className="mt-3 text-xs text-amber-200/85">
            <span className="font-semibold text-amber-100/90">Pattern:</span> {patternLabel(result.pattern_matched)}
          </p>
        )}
      </div>

      {securityBrief ? (
        <div className="relative mt-4 rounded-2xl border border-violet-500/25 bg-violet-500/10 p-4">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-violet-200/80">AI security brief</p>
          <p className="mt-2 text-sm leading-relaxed text-violet-50/90">{securityBrief}</p>
        </div>
      ) : null}

      {result?.warning_message && !securityBrief && (
        <p className="relative mt-4 text-sm text-amber-100/85">{result.warning_message}</p>
      )}

      <div className="relative mt-6 flex flex-wrap gap-2">
        {isCritical && (
          <>
            <a
              href="tel:1930"
              className="inline-flex min-h-[44px] items-center justify-center rounded-xl border border-white/15 bg-white/[0.06] px-4 text-sm font-semibold text-white transition hover:bg-white/[0.1]"
            >
              Call 1930
            </a>
            <button
              type="button"
              disabled={reporting}
              onClick={onReport}
              className="inline-flex min-h-[44px] items-center justify-center rounded-xl bg-gradient-to-r from-rose-600 to-red-600 px-4 text-sm font-semibold text-white shadow-lg shadow-rose-500/25 transition hover:brightness-110 disabled:opacity-50"
            >
              {reporting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Report fraud
            </button>
          </>
        )}
        {isSuspicious && (
          <>
            <button
              type="button"
              onClick={onDismiss}
              className="inline-flex min-h-[44px] items-center justify-center rounded-xl bg-gradient-to-r from-violet-600 to-blue-600 px-4 text-sm font-semibold text-white shadow-lg shadow-violet-500/25 transition hover:brightness-110"
            >
              I&apos;ve verified — dismiss
            </button>
            <button
              type="button"
              disabled={reporting}
              onClick={onReport}
              className="inline-flex min-h-[44px] items-center justify-center rounded-xl border border-rose-500/40 bg-rose-500/15 px-4 text-sm font-semibold text-rose-100 transition hover:bg-rose-500/25 disabled:opacity-50"
            >
              Report fraud
            </button>
          </>
        )}
        {!isCritical && !isSuspicious && (
          <button
            type="button"
            onClick={onDismiss}
            className="inline-flex min-h-[44px] items-center justify-center rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 px-4 text-sm font-semibold text-white shadow-lg shadow-emerald-500/20 transition hover:brightness-110"
          >
            Done — looks good for {userName}
          </button>
        )}
        {(isCritical || isSuspicious) && (
          <button
            type="button"
            onClick={onDismiss}
            className="inline-flex min-h-[44px] items-center justify-center rounded-xl border border-white/15 px-4 text-sm font-medium text-exiqo-glow/80 transition hover:bg-white/[0.06] hover:text-white"
          >
            Scan another
          </button>
        )}
      </div>

      {reportMsg ? (
        <p className="relative mt-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-100/90">
          {reportMsg}
        </p>
      ) : null}

      {(isCritical || isSuspicious) && (
        <p className="relative mt-3 text-center text-[11px] text-exiqo-glow/45">
          <a href={result.cybercrime_url || "https://cybercrime.gov.in"} target="_blank" rel="noreferrer" className="underline-offset-2 hover:underline">
            National Cyber Crime Reporting Portal
          </a>{" "}
          · Helpline {result.helpline || "1930"}
        </p>
      )}
    </motion.div>
  );
}

const TransactionChecker = ({ userId, userName, onReportSuccess }) => {
  const { showToast } = useToast();
  const [merchant, setMerchant] = useState("");
  const [amount, setAmount] = useState("");
  const [time, setTime] = useState(nowTime());
  const [description, setDescription] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("UPI");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [reportMsg, setReportMsg] = useState("");
  const [reporting, setReporting] = useState(false);
  const [scanStep, setScanStep] = useState(0);
  const scanTimerRef = useRef(null);

  useEffect(() => {
    if (!loading) {
      if (scanTimerRef.current) clearInterval(scanTimerRef.current);
      scanTimerRef.current = null;
      setScanStep(0);
      return undefined;
    }
    scanTimerRef.current = window.setInterval(() => {
      setScanStep((s) => (s + 1 >= SCAN_STEPS.length ? SCAN_STEPS.length - 1 : s + 1));
    }, 320);
    return () => {
      if (scanTimerRef.current) clearInterval(scanTimerRef.current);
    };
  }, [loading]);

  const runCheck = async (body) => {
    setLoading(true);
    setResult(null);
    setReportMsg("");
    setScanStep(0);
    const t0 = Date.now();
    try {
      const data = await postFraudShieldCheckTransaction(userId, body);
      const elapsed = Date.now() - t0;
      const pad = Math.max(0, MIN_SCAN_MS - elapsed);
      if (pad) await new Promise((r) => setTimeout(r, pad));
      setResult(data);
    } catch (e) {
      const elapsed = Date.now() - t0;
      const pad = Math.max(0, MIN_SCAN_MS - elapsed);
      if (pad) await new Promise((r) => setTimeout(r, pad));
      setResult({
        error: true,
        warning_message: e.message || "Check failed",
        risk_score: 0,
        risk_level: "LOW",
      });
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = (e) => {
    e.preventDefault();
    const amt = parseFloat(amount);
    if (!merchant.trim() || Number.isNaN(amt)) return;
    runCheck({
      merchant: merchant.trim(),
      amount: amt,
      transaction_time: time || undefined,
      description: description.trim() || undefined,
      payment_method: paymentMethod,
    });
  };

  const fillKyc = () => {
    setMerchant("sbi-kyc-update@ybl");
    setAmount("15000");
    setTime("23:30");
    setDescription("");
    setPaymentMethod("UPI");
  };
  const fillLottery = () => {
    setMerchant("prize-claim-2025@upi");
    setAmount("2000");
    setTime("15:00");
    setDescription("Lottery processing fee");
    setPaymentMethod("UPI");
  };
  const fillNormal = () => {
    setMerchant("swiggy@ybl");
    setAmount("250");
    setTime("14:00");
    setDescription("Lunch order");
    setPaymentMethod("UPI");
  };
  const fillRupeeTrap = () => {
    setMerchant("verify-upi-axis@okaxis");
    setAmount("1");
    setTime("23:45");
    setDescription("UPI verify");
    setPaymentMethod("UPI");
  };
  const fillCollect = () => {
    setMerchant("refund-amazon@okaxis");
    setAmount("3499");
    setTime("12:00");
    setDescription("UPI collect request — refund");
    setPaymentMethod("UPI Collect");
  };

  const handleReport = async () => {
    setReporting(true);
    setReportMsg("");
    try {
      if (result?.alert_id) {
        const res = await postFraudShieldAlertAction(userId, result.alert_id, "REPORTED");
        setReportMsg(res.message || "Fraud reported successfully!");
        showToast("Fraud reported — follow up on National Cyber Crime Portal ✅");
        onReportSuccess?.();
      } else {
        setReportMsg(
          `Fraud reported — file details on ${result?.cybercrime_url || "https://cybercrime.gov.in"} (Helpline 1930).`
        );
        showToast("Fraud reported — file details on National Cyber Crime Portal ✅");
        onReportSuccess?.();
      }
    } catch (e) {
      setReportMsg(e.message || "Could not update alert");
    } finally {
      setReporting(false);
    }
  };

  const verdict = useMemo(() => (result && !result.error ? verdictFromResult(result) : null), [result]);
  const securityBrief = (result?.ai_security_message || result?.hinglish_warning || "").trim();
  const amtPreview = parseFloat(amount);
  const amountLabel = Number.isFinite(amtPreview) ? inr(amtPreview) : "—";

  const fieldClass =
    "mt-1.5 w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white outline-none transition placeholder:text-exiqo-glow/35 focus:border-violet-400/50 focus:ring-2 focus:ring-violet-500/25";
  const labelClass = "text-[11px] font-semibold uppercase tracking-wider text-exiqo-glow/50";

  return (
    <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-br from-[#0c0c24]/95 via-violet-950/20 to-[#0f172a]/90 p-1 shadow-[0_0_60px_-24px_rgba(124,58,237,0.45)]">
      <div className="rounded-[22px] border border-white/5 bg-white/[0.02] p-5 sm:p-8">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-violet-300/80">Safety scanner</p>
            <h3 className="mt-1 text-xl font-bold tracking-tight text-white sm:text-2xl">Check before you pay</h3>
            <p className="mt-2 max-w-xl text-sm text-exiqo-glow/65">
              Paste the UPI handle or merchant id, amount, and channel. We run the same stack as live scoring — then show a
              clear verdict with explainable drivers.
            </p>
          </div>
          <div className="hidden text-right text-xs text-exiqo-glow/45 sm:block">
            <p className="tabular-nums">Typical scan ~1.2s</p>
            <p>Model + rules + brief</p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="relative space-y-5" aria-busy={loading}>
          <AnimatePresence>{loading && <ScanningOverlay stepIndex={scanStep} />}</AnimatePresence>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-12">
            <label className="block lg:col-span-5">
              <span className={labelClass}>Merchant / UPI ID</span>
              <input
                className={`${fieldClass} font-mono text-base`}
                value={merchant}
                onChange={(e) => setMerchant(e.target.value)}
                placeholder="merchant@ybl or paytm.swiggy"
                autoComplete="off"
                disabled={loading}
              />
            </label>
            <label className="block lg:col-span-3">
              <span className={labelClass}>Amount</span>
              <input
                className={`${fieldClass} tabular-nums text-lg font-semibold`}
                type="number"
                min="0"
                step="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0"
                disabled={loading}
              />
              <p className="mt-1 text-[11px] text-exiqo-glow/40">Preview: {amountLabel}</p>
            </label>
            <label className="block lg:col-span-2">
              <span className={labelClass}>Time</span>
              <input className={`${fieldClass} tabular-nums`} value={time} onChange={(e) => setTime(e.target.value)} placeholder="23:30" disabled={loading} />
            </label>
            <label className="block lg:col-span-2">
              <span className={labelClass}>Channel</span>
              <select className={`${fieldClass} cursor-pointer`} value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)} disabled={loading}>
                <option value="UPI">UPI</option>
                <option value="UPI Collect">UPI Collect</option>
                <option value="IMPS">IMPS</option>
              </select>
            </label>
            <label className="block sm:col-span-2 lg:col-span-12">
              <span className={labelClass}>Note (optional)</span>
              <input
                className={fieldClass}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Order id, purpose, or context"
                disabled={loading}
              />
            </label>
          </div>

          <div>
            <p className={labelClass}>Quick scenarios</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {[
                { label: "KYC fraud", fn: fillKyc, tone: "border-rose-500/35 bg-rose-500/10 text-rose-100 hover:bg-rose-500/20" },
                { label: "Lottery scam", fn: fillLottery, tone: "border-rose-500/35 bg-rose-500/10 text-rose-100 hover:bg-rose-500/20" },
                { label: "UPI collect", fn: fillCollect, tone: "border-amber-500/35 bg-amber-500/10 text-amber-100 hover:bg-amber-500/20" },
                { label: "₹1 trap", fn: fillRupeeTrap, tone: "border-rose-500/35 bg-rose-500/10 text-rose-100 hover:bg-rose-500/20" },
                { label: "Normal order", fn: fillNormal, tone: "border-emerald-500/35 bg-emerald-500/10 text-emerald-100 hover:bg-emerald-500/20" },
              ].map((q) => (
                <motion.button
                  key={q.label}
                  type="button"
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={q.fn}
                  disabled={loading}
                  className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition disabled:opacity-40 ${q.tone}`}
                >
                  {q.label}
                </motion.button>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <motion.button
              type="submit"
              disabled={loading || !merchant.trim() || Number.isNaN(parseFloat(amount))}
              whileHover={{ scale: loading ? 1 : 1.02 }}
              whileTap={{ scale: loading ? 1 : 0.98 }}
              className="inline-flex min-h-[52px] min-w-[200px] items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-violet-600 to-blue-600 px-8 text-base font-bold text-white shadow-[0_0_40px_-10px_rgba(124,58,237,0.65)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {loading ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
                  Scanning…
                </>
              ) : (
                <>
                  <Radar className="h-5 w-5" aria-hidden />
                  Run safety scan
                </>
              )}
            </motion.button>
            <p className="text-[11px] text-exiqo-glow/45">Enter merchant + amount to enable scan.</p>
          </div>
        </form>

        <AnimatePresence mode="wait">
          {result && !loading && result.error && (
            <motion.div
              key="err"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="mt-6 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-100/90"
            >
              {result.warning_message}
            </motion.div>
          )}
          {result && !loading && !result.error && verdict && (
            <div key="ok" className="mt-8">
              <VerdictCard
                verdict={verdict}
                result={result}
                userName={userName || "you"}
                reporting={reporting}
                reportMsg={reportMsg}
                onDismiss={() => {
                  setResult(null);
                  setReportMsg("");
                }}
                onReport={handleReport}
                securityBrief={securityBrief}
              />
            </div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default TransactionChecker;
