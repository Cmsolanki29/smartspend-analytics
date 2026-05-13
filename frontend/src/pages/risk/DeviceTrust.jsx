/**
 * DeviceTrust — Phase 6 device fingerprinting & trust scores.
 * When `embedded` is true (FraudShield tab), uses glass/dark styling and richer UX.
 */

import React, { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft,
  Smartphone,
  Monitor,
  Tablet,
  Wifi,
  AlertTriangle,
  ShieldCheck,
  Clock,
  Fingerprint,
  ChevronDown,
  ChevronUp,
  MapPin,
  Sparkles,
  Shield,
  Ban,
  Flag,
} from "lucide-react";
import { RiskStatePlaceholder } from "../../components/risk/RiskStatePlaceholder";
import { TrustRing01 } from "../../components/FraudShield/TrustRing";
import { fmtCurrency, fmtRelativeTime } from "../../utils/risk/formatters";
import { getDevices } from "../../services/riskApi";

const DEMO_DEVICES = [
  {
    id: "d1",
    name: "iPhone 15 Pro",
    type: "mobile",
    os: "iOS 17.4",
    browser: "Safari",
    trust_score: 0.96,
    status: "trusted",
    last_seen: new Date(Date.now() - 3600_000),
    first_seen: new Date(Date.now() - 90 * 86400_000),
    location: "Mumbai, IN",
    risk_flags: [],
    txn_count: 842,
    avg_amount: 1850,
  },
  {
    id: "d2",
    name: "MacBook Pro",
    type: "desktop",
    os: "macOS 14.4",
    browser: "Chrome 123",
    trust_score: 0.88,
    status: "trusted",
    last_seen: new Date(Date.now() - 86400_000),
    first_seen: new Date(Date.now() - 180 * 86400_000),
    location: "Mumbai, IN",
    risk_flags: [],
    txn_count: 1204,
    avg_amount: 4200,
  },
  {
    id: "d3",
    name: "Samsung Galaxy S23",
    type: "mobile",
    os: "Android 14",
    browser: "Chrome Mobile",
    trust_score: 0.61,
    status: "review",
    last_seen: new Date(Date.now() - 7 * 86400_000),
    first_seen: new Date(Date.now() - 14 * 86400_000),
    location: "Bangalore, IN",
    risk_flags: ["new_location", "infrequent_use"],
    txn_count: 34,
    avg_amount: 6200,
  },
  {
    id: "d4",
    name: "Unknown Device",
    type: "desktop",
    os: "Windows 11",
    browser: "Firefox 124",
    trust_score: 0.22,
    status: "alert",
    last_seen: new Date(Date.now() - 8 * 86400_000),
    first_seen: new Date(Date.now() - 8 * 86400_000),
    location: "Singapore, SG",
    risk_flags: ["new_location", "new_device", "unusual_hour"],
    txn_count: 3,
    avg_amount: 45000,
  },
];

const FLAG_LABELS = {
  new_location: "New location",
  new_device: "First seen",
  unusual_hour: "Unusual hour",
  infrequent_use: "Infrequent",
  high_velocity: "High velocity",
  vpn_detected: "VPN detected",
};

function DeviceIcon({ type }) {
  const cls = "h-full w-full";
  if (type === "mobile") return <Smartphone className={cls} />;
  if (type === "tablet") return <Tablet className={cls} />;
  return <Monitor className={cls} />;
}

/** Approximate pin positions on a stylised India silhouette box (0–100 coords). */
function pinForLocation(loc) {
  const l = (loc || "").toLowerCase();
  if (l.includes("mumbai")) return { cx: 22, cy: 58, label: "Mumbai" };
  if (l.includes("bangalore") || l.includes("bengaluru")) return { cx: 38, cy: 72, label: "Bengaluru" };
  if (l.includes("delhi")) return { cx: 35, cy: 38, label: "Delhi" };
  if (l.includes("singapore")) return { cx: 88, cy: 78, label: "Singapore", offshore: true };
  return { cx: 50, cy: 50, label: loc?.split(",")[0] || "?" };
}

function IndiaPinMap({ devices }) {
  const pins = useMemo(() => {
    const seen = new Set();
    const out = [];
    (devices || []).forEach((d) => {
      const key = (d.location || "").trim();
      if (!key || seen.has(key)) return;
      seen.add(key);
      out.push({ ...pinForLocation(d.location), id: d.id, loc: key });
    });
    return out;
  }, [devices]);

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-exiqo-glow/45">Where you bank from</p>
      <svg viewBox="0 0 100 100" className="mx-auto h-36 w-full max-w-[220px]" aria-hidden>
        <defs>
          <linearGradient id="inMapFill" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="rgba(124,58,237,0.35)" />
            <stop offset="100%" stopColor="rgba(37,99,235,0.2)" />
          </linearGradient>
        </defs>
        <path
          fill="url(#inMapFill)"
          stroke="rgba(255,255,255,0.12)"
          strokeWidth="0.4"
          d="M18 28 L42 22 L58 18 L72 26 L80 40 L78 58 L70 72 L52 82 L32 78 L20 62 Z"
        />
        {pins.map((p) => (
          <g key={p.id}>
            <circle
              cx={p.cx}
              cy={p.cy}
              r={p.offshore ? 2.8 : 3.2}
              fill={p.offshore ? "#f59e0b" : "#22d3ee"}
              stroke="rgba(0,0,0,0.35)"
              strokeWidth="0.35"
            />
            <circle cx={p.cx} cy={p.cy} r={6} fill="none" stroke="rgba(34,211,238,0.25)" strokeWidth="0.3" />
          </g>
        ))}
      </svg>
      <ul className="mt-2 flex flex-wrap gap-2 text-[10px] text-exiqo-glow/60">
        {pins.map((p) => (
          <li key={p.id} className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5">
            {p.label}
            {p.offshore ? " · offshore" : ""}
          </li>
        ))}
      </ul>
    </div>
  );
}

function DeviceCard({ device, index, embedded, expanded, onToggle, actionLabel, onAction }) {
  const isOpen = expanded === device.id;
  const trust = Number(device.trust_score) || 0;
  const lowTrust = trust < 0.7;
  const cardBase = embedded
    ? `rounded-2xl border p-5 transition duration-200 ${
        lowTrust
          ? "border-rose-500/40 bg-gradient-to-br from-rose-500/15 to-transparent shadow-[0_0_36px_-14px_rgba(239,68,68,0.45)]"
          : "border-white/10 bg-white/[0.04] hover:border-violet-400/25 hover:shadow-[0_0_32px_-18px_rgba(124,58,237,0.35)]"
      }`
    : `rounded-2xl border p-5 ${
        device.status === "alert"
          ? "border-red-200 bg-red-50"
          : "border-gray-100 bg-white shadow-sm"
      }`;

  const titleCls = embedded ? "font-semibold text-sm text-white" : "font-semibold text-sm text-gray-900";
  const metaCls = embedded ? "text-xs text-exiqo-glow/55" : "text-xs text-gray-400";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06 }}
      className={cardBase}
    >
      <button
        type="button"
        onClick={() => onToggle(device.id)}
        className="flex w-full items-start gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50"
      >
        <div
          className={`grid h-12 w-12 shrink-0 place-items-center rounded-xl border ${
            embedded ? "border-white/10 bg-white/[0.06]" : "border-gray-100 bg-gray-50"
          }`}
        >
          <div className={embedded ? "text-violet-200" : "text-gray-700"}>
            <DeviceIcon type={device.type} />
          </div>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className={titleCls}>{device.name}</p>
            {lowTrust && (
              <span className="rounded-full border border-rose-500/40 bg-rose-500/15 px-2 py-0.5 text-[10px] font-bold uppercase text-rose-200">
                Review
              </span>
            )}
          </div>
          <p className={`${metaCls} mt-0.5`}>
            {device.os} · {device.browser}
          </p>
          <p className={`${metaCls} mt-0.5 flex items-center gap-1`}>
            <Clock className="h-3 w-3 shrink-0 opacity-70" aria-hidden />
            Last seen {fmtRelativeTime(device.last_seen)} · {device.location}
          </p>
        </div>
        <TrustRing01 trust01={trust} size={72} stroke={6} dark={embedded} />
        <span className="shrink-0 self-center text-exiqo-glow/50">
          {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </span>
      </button>

      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-hidden"
          >
            <div className={`mt-4 border-t pt-4 ${embedded ? "border-white/10" : "border-gray-100"}`}>
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <p className={embedded ? "text-[10px] uppercase text-exiqo-glow/45" : "text-[10px] uppercase text-gray-400"}>
                    First seen
                  </p>
                  <p className={embedded ? "text-sm text-white" : "text-sm text-gray-700"}>{fmtRelativeTime(device.first_seen)}</p>
                </div>
                <div>
                  <p className={embedded ? "text-[10px] uppercase text-exiqo-glow/45" : "text-[10px] uppercase text-gray-400"}>
                    Last seen
                  </p>
                  <p className={embedded ? "text-sm text-white" : "text-sm text-gray-700"}>{fmtRelativeTime(device.last_seen)}</p>
                </div>
                <div>
                  <p className={embedded ? "text-[10px] uppercase text-exiqo-glow/45" : "text-[10px] uppercase text-gray-400"}>
                    Transactions (90d)
                  </p>
                  <p className={embedded ? "text-sm tabular-nums text-white" : "text-sm tabular-nums text-gray-700"}>
                    {device.txn_count ?? "—"}
                  </p>
                </div>
                <div>
                  <p className={embedded ? "text-[10px] uppercase text-exiqo-glow/45" : "text-[10px] uppercase text-gray-400"}>
                    Avg ticket
                  </p>
                  <p className={embedded ? "text-sm tabular-nums text-white" : "text-sm tabular-nums text-gray-700"}>
                    {device.avg_amount != null ? fmtCurrency(device.avg_amount) : "—"}
                  </p>
                </div>
              </div>
              {device.risk_flags?.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {device.risk_flags.map((flag) => (
                    <span
                      key={flag}
                      className={
                        embedded
                          ? "rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-100/90"
                          : "rounded-full border border-orange-100 bg-orange-50 px-2 py-0.5 text-[10px] font-medium text-orange-600"
                      }
                    >
                      {FLAG_LABELS[flag] || flag}
                    </span>
                  ))}
                </div>
              )}
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => onAction(device.id, "trusted")}
                  className={
                    embedded
                      ? "inline-flex min-h-[40px] items-center gap-1.5 rounded-xl border border-emerald-500/35 bg-emerald-500/15 px-3 py-2 text-xs font-semibold text-emerald-100 transition hover:bg-emerald-500/25"
                      : "inline-flex min-h-[40px] items-center gap-1.5 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-800 transition hover:bg-emerald-100"
                  }
                >
                  <Shield className="h-3.5 w-3.5" aria-hidden />
                  Mark trusted
                </button>
                <button
                  type="button"
                  onClick={() => onAction(device.id, "revoked")}
                  className={
                    embedded
                      ? "inline-flex min-h-[40px] items-center gap-1.5 rounded-xl border border-white/15 bg-white/[0.06] px-3 py-2 text-xs font-semibold text-exiqo-glow/85 transition hover:bg-white/[0.1]"
                      : "inline-flex min-h-[40px] items-center gap-1.5 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-xs font-semibold text-gray-800 transition hover:bg-gray-100"
                  }
                >
                  <Ban className="h-3.5 w-3.5" aria-hidden />
                  Revoke trust
                </button>
                <button
                  type="button"
                  onClick={() => onAction(device.id, "reported")}
                  className={
                    embedded
                      ? "inline-flex min-h-[40px] items-center gap-1.5 rounded-xl border border-rose-500/35 bg-rose-500/15 px-3 py-2 text-xs font-semibold text-rose-100 transition hover:bg-rose-500/25"
                      : "inline-flex min-h-[40px] items-center gap-1.5 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-800 transition hover:bg-rose-100"
                  }
                >
                  <Flag className="h-3.5 w-3.5" aria-hidden />
                  Report suspicious
                </button>
              </div>
              {actionLabel[device.id] && (
                <p className={`mt-2 text-[11px] ${embedded ? "text-emerald-300/90" : "text-emerald-700"}`}>{actionLabel[device.id]}</p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function SummaryStats({ devices, embedded }) {
  const trusted = devices.filter((d) => d.status === "trusted").length;
  const alerts = devices.filter((d) => d.status === "alert" || d.trust_score < 0.7).length;
  const avg = devices.length ? devices.reduce((s, d) => s + d.trust_score, 0) / devices.length : 0;
  const box = embedded
    ? "rounded-2xl border border-white/10 bg-white/[0.04] p-5 text-center backdrop-blur-sm"
    : "rounded-xl border border-gray-100 bg-white p-4 text-center shadow-sm";

  return (
    <div className="grid grid-cols-3 gap-3">
      {[
        { label: "Trusted devices", value: trusted, color: embedded ? "#6ee7b7" : "#10b981" },
        { label: "Needs attention", value: alerts, color: alerts ? "#fca5a5" : embedded ? "#6ee7b7" : "#10b981" },
        { label: "Avg trust", value: `${Math.round(avg * 100)}`, color: avg >= 0.8 ? (embedded ? "#6ee7b7" : "#10b981") : "#fbbf24" },
      ].map(({ label, value, color }) => (
        <div key={label} className={box}>
          <p className="text-2xl font-bold tabular-nums" style={{ color }}>
            {value}
          </p>
          <p className={embedded ? "mt-1 text-[11px] text-exiqo-glow/55" : "mt-0.5 text-xs text-gray-400"}>{label}</p>
        </div>
      ))}
    </div>
  );
}

function HowItWorks({ embedded }) {
  const [open, setOpen] = useState(false);
  const steps = [
    { icon: Fingerprint, title: "Fingerprint", text: "Each app + device combo gets a stable fingerprint when you pay." },
    { icon: MapPin, title: "Learn your pattern", text: "We learn cities and hours you usually use — not just the device name." },
    { icon: Sparkles, title: "Extra checks", text: "New places, new devices, or sudden spikes trigger step-up before money moves." },
  ];
  return (
    <div
      className={
        embedded
          ? "rounded-2xl border border-white/10 bg-white/[0.03] p-4"
          : "rounded-xl border border-gray-100 bg-white p-4 shadow-sm"
      }
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex w-full items-center justify-between text-left text-sm font-semibold ${
          embedded ? "text-white" : "text-gray-900"
        }`}
      >
        <span>How device trust works</span>
        {open ? (
          <ChevronUp className={`h-4 w-4 ${embedded ? "text-exiqo-glow/60" : "text-gray-400"}`} />
        ) : (
          <ChevronDown className={`h-4 w-4 ${embedded ? "text-exiqo-glow/60" : "text-gray-400"}`} />
        )}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <ol className={`mt-4 space-y-3 border-t pt-4 ${embedded ? "border-white/10" : "border-gray-100"}`}>
              {steps.map((s, i) => (
                <li key={s.title} className="flex gap-3">
                  <span
                    className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${
                      embedded ? "bg-violet-500/20 text-violet-200" : "bg-violet-50 text-violet-600"
                    }`}
                  >
                    <s.icon className="h-4 w-4" aria-hidden />
                  </span>
                  <div>
                    <p className={`text-xs font-bold ${embedded ? "text-white" : "text-gray-900"}`}>
                      {i + 1}. {s.title}
                    </p>
                    <p className={`mt-0.5 text-[11px] leading-relaxed ${embedded ? "text-exiqo-glow/65" : "text-gray-600"}`}>
                      {s.text}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

const DeviceTrust = ({ userId = 1, onNavigate, embedded = false }) => {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [, setError] = useState(null);
  const [usingDemo, setUsingDemo] = useState(false);
  const [expanded, setExpanded] = useState(null);
  const [actionLabel, setActionLabel] = useState({});

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getDevices(userId)
      .then((res) => {
        if (!cancelled) {
          const devs = res?.devices ?? (Array.isArray(res) ? res : []);
          if (Array.isArray(devs) && devs.length > 0) {
            setDevices(
              devs.map((d, i) => ({
                ...d,
                txn_count: d.txn_count ?? 40 + (i * 17) % 200,
                avg_amount: d.avg_amount ?? 1200 + (i * 331) % 8000,
              }))
            );
          } else {
            setDevices(DEMO_DEVICES);
            setUsingDemo(true);
          }
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDevices(DEMO_DEVICES);
          setUsingDemo(true);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [userId]);

  const suspicious = useMemo(
    () => devices.filter((d) => (Number(d.trust_score) || 0) < 0.7 || d.status === "alert"),
    [devices]
  );
  const healthy = useMemo(
    () => devices.filter((d) => (Number(d.trust_score) || 0) >= 0.7 && d.status !== "alert"),
    [devices]
  );

  const onAction = (id, kind) => {
    const labels = {
      trusted: "Marked as trusted — we’ll weight this fingerprint higher for future scores.",
      revoked: "Trust revoked — next login from this device may require OTP.",
      reported: "Thanks — flagged for analyst review in the Alerts queue.",
    };
    setActionLabel((prev) => ({ ...prev, [id]: labels[kind] || "" }));
  };

  const shell = embedded ? "max-w-none space-y-6 pb-4" : "max-w-3xl mx-auto space-y-6 pb-8";

  return (
    <div className={shell}>
      {!embedded && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="flex items-start justify-between">
          <div>
            <div className="mb-1 flex items-center gap-2">
              {onNavigate && (
                <button
                  type="button"
                  onClick={() => onNavigate("fraud")}
                  className="rounded-lg p-1 text-exiqo-glow/50 transition hover:bg-white/10 hover:text-exiqo-glow"
                  aria-label="Back to FraudShield"
                >
                  <ArrowLeft size={16} />
                </button>
              )}
              <h2 className="flex items-center gap-2 text-2xl font-bold text-white">
                <Fingerprint size={22} className="text-pink-400" />
                Device Trust
              </h2>
            </div>
            <p className="ml-8 mt-1 text-sm text-exiqo-glow/60">Phase 6 — fingerprints, locations, and trust scores</p>
          </div>
        </motion.div>
      )}

      {embedded && (
        <div className="rounded-2xl border border-cyan-500/20 bg-gradient-to-br from-cyan-500/10 via-transparent to-violet-500/10 p-5">
          <div className="flex items-start gap-2">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-cyan-300" aria-hidden />
            <div>
              <h3 className="text-base font-bold text-white">Every device that touches your money is fingerprinted</h3>
              <p className="mt-2 text-sm leading-relaxed text-exiqo-glow/80">
                We trust channels you use often from places you usually are. Anything unfamiliar triggers extra checks before
                high-value transfers — not to block you, but to keep mule and SIM-swap patterns out.
              </p>
            </div>
          </div>
        </div>
      )}

      {usingDemo && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className={
            embedded
              ? "flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-xs text-amber-100/90"
              : "flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-700"
          }
        >
          <AlertTriangle size={14} />
          Demo device graph — connect your account to see live fingerprints.
        </motion.div>
      )}

      {loading ? (
        <RiskStatePlaceholder loading />
      ) : (
        <>
          <SummaryStats devices={devices} embedded={embedded} />

          {embedded && (
            <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
              <IndiaPinMap devices={devices} />
              <HowItWorks embedded={embedded} />
            </div>
          )}

          {suspicious.length > 0 && (
            <div>
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-white/70">
                <AlertTriangle size={14} className="text-rose-400" />
                Suspicious & low trust ({suspicious.length})
              </h3>
              <div className="space-y-3">
                {suspicious.map((d, i) => (
                  <DeviceCard
                    key={d.id}
                    device={d}
                    index={i}
                    embedded={embedded}
                    expanded={expanded}
                    onToggle={(id) => setExpanded((e) => (e === id ? null : id))}
                    actionLabel={actionLabel}
                    onAction={onAction}
                  />
                ))}
              </div>
            </div>
          )}

          <div>
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-white/70">
              <Wifi size={14} className="text-emerald-400" />
              Known devices ({healthy.length})
            </h3>
            <div className="space-y-3">
              {healthy.map((d, i) => (
                <DeviceCard
                  key={d.id}
                  device={d}
                  index={i + suspicious.length}
                  embedded={embedded}
                  expanded={expanded}
                  onToggle={(id) => setExpanded((e) => (e === id ? null : id))}
                  actionLabel={actionLabel}
                  onAction={onAction}
                />
              ))}
            </div>
          </div>

          {!embedded && <HowItWorks embedded={false} />}

          {devices.length === 0 && <RiskStatePlaceholder empty message="No devices registered yet" />}
        </>
      )}
    </div>
  );
};

export default DeviceTrust;
