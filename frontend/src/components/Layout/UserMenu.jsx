/**
 * UserMenu — Profile avatar chip + dropdown with backdrop.
 */
import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  ChevronDown,
  CreditCard,
  ExternalLink,
  FileText,
  HelpCircle,
  Landmark,
  LogOut,
  Mail,
  UserCircle,
  Zap,
} from "lucide-react";
import useEscapeKey from "../../hooks/useEscapeKey";
import useClickOutside from "../../hooks/useClickOutside";
import { getConnectedSources } from "../../services/api";
import { useAuth } from "../../context/AuthContext";

const MENU_ITEMS = [
  {
    id: "settings",
    label: "Account & Settings",
    icon: UserCircle,
    description: "Profile, preferences & config",
  },
  null,
  {
    id: "_help",
    label: "Help & Support",
    icon: HelpCircle,
    description: "Docs, FAQs & contact",
    external: true,
  },
  {
    id: "_logout",
    label: "Sign out",
    icon: LogOut,
    danger: true,
  },
];

function useLockBodyScroll(active) {
  useEffect(() => {
    if (!active) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = original;
    };
  }, [active]);
}

function labelSourceType(type) {
  const t = String(type || "").toLowerCase();
  if (t.includes("credit")) return "Credit card";
  if (t.includes("bank")) return "Bank account";
  return t.replace(/_/g, " ") || "Account";
}

function labelAddedVia(via) {
  const v = String(via || "").toLowerCase();
  if (v === "bank") return "Linked at signup";
  if (v === "bank_statement_pdf" || v === "bank_statement") return "Bank statement PDF";
  if (v === "credit_card" || v === "credit_card_statement") return "Credit card statement";
  if (v === "onboarding") return "Onboarding";
  if (v === "skipped") return "Skipped — no data yet";
  if (!v) return "Connected";
  return v.replace(/_/g, " ");
}

function formatInstitution(name) {
  const n = String(name || "").trim();
  if (!n) return "Unknown institution";
  if (/^axis$/i.test(n)) return "Axis Bank";
  if (/^hdfc$/i.test(n)) return "HDFC Bank";
  if (/^sbi$/i.test(n)) return "State Bank of India";
  if (/^icici$/i.test(n)) return "ICICI Bank";
  if (/^kotak$/i.test(n)) return "Kotak Mahindra Bank";
  return n;
}

function LinkedAccountRow({ source }) {
  const isCard = String(source.source_type || "").includes("credit");
  const Icon = isCard ? CreditCard : Landmark;
  return (
    <li className="flex items-start gap-2.5 rounded-lg border border-white/[0.06] bg-white/[0.03] px-2.5 py-2">
      <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-md bg-white/[0.06] text-white/80">
        <Icon className="h-3.5 w-3.5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-semibold text-white">{formatInstitution(source.institution_name)}</p>
        <p className="mt-0.5 text-[10px] leading-snug text-gray-400">
          {labelSourceType(source.source_type)}
          {source.account_number_masked ? ` · ${source.account_number_masked}` : ""}
        </p>
        <p className="mt-0.5 text-[10px] text-gray-500">{labelAddedVia(source.added_via)}</p>
        {source.last_upload ? (
          <p className="mt-0.5 text-[10px] text-gray-600">
            Last statement: {new Date(source.last_upload).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
          </p>
        ) : null}
      </div>
      {source.is_primary ? (
        <span className="shrink-0 rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-emerald-300">
          Primary
        </span>
      ) : null}
    </li>
  );
}

const UserMenu = ({ userName = "User", userEmail, userId, onTabChange, onLogout }) => {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [dropPos, setDropPos] = useState({ top: 0, right: 0 });
  const [sources, setSources] = useState([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourcesErr, setSourcesErr] = useState("");
  const triggerRef = useRef(null);
  const dropdownRef = useRef(null);

  const close = () => setOpen(false);
  const uid = Number(userId) || Number(user?.id) || 0;
  const profileBank = user?.bank || null;

  useEscapeKey(open, close);
  useClickOutside([triggerRef, dropdownRef], open ? close : null);
  useLockBodyScroll(open);

  useEffect(() => {
    if (!open || !triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    setDropPos({
      top: rect.bottom + 8,
      right: Math.max(8, window.innerWidth - rect.right),
    });
  }, [open]);

  useEffect(() => {
    if (!open || !uid) {
      return;
    }
    let cancelled = false;
    setSourcesLoading(true);
    setSourcesErr("");
    getConnectedSources(uid)
      .then((data) => {
        if (cancelled) return;
        setSources(Array.isArray(data?.sources) ? data.sources : []);
      })
      .catch((e) => {
        if (cancelled) return;
        setSources([]);
        setSourcesErr(e?.message || "Could not load linked accounts");
      })
      .finally(() => {
        if (!cancelled) setSourcesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, uid]);

  const displayName = userName?.trim() || "User";
  const parts = displayName.split(" ").filter(Boolean);
  const avatarText =
    parts.length > 1
      ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
      : displayName.charAt(0).toUpperCase();

  const handleItem = (item) => {
    close();
    if (item.id === "_logout") {
      onLogout?.();
      return;
    }
    if (item.id === "_help") {
      window.open("https://cybercrime.gov.in", "_blank");
      return;
    }
    onTabChange?.(item.id);
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${displayName}`}
        className={`flex h-10 shrink-0 items-center gap-2 rounded-full border p-1 transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/50 md:pr-3 ${
          open
            ? "border-purple-400/50 bg-purple-500/15 shadow-[0_0_24px_-6px_rgba(139,92,246,0.6)]"
            : "border-white/10 bg-white/[0.04] hover:border-purple-400/30 hover:bg-white/[0.07] hover:shadow-[0_0_16px_-8px_rgba(139,92,246,0.35)]"
        }`}
      >
        <span
          className={`relative grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-purple-500 to-purple-700 text-[11px] font-bold text-white transition-shadow duration-300 ${
            open
              ? "shadow-[0_0_18px_-2px_rgba(139,92,246,0.8)]"
              : "shadow-[0_0_10px_-4px_rgba(139,92,246,0.5)]"
          }`}
        >
          {avatarText}
          <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-[#070418] bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]" />
        </span>

        <span className="hidden flex-col items-start leading-none md:flex">
          <span className="max-w-[7.5rem] truncate text-[13px] font-medium leading-tight text-white/90">
            {displayName}
          </span>
          <span className="mt-0.5 flex items-center gap-0.5 text-[10px] font-semibold tracking-wide text-purple-400">
            <Zap size={8} aria-hidden />
            Premium
          </span>
        </span>

        <ChevronDown
          size={14}
          className={`hidden text-white/40 transition-transform duration-200 md:block ${open ? "rotate-180" : ""}`}
          aria-hidden
        />
      </button>

      {createPortal(
        <AnimatePresence>
          {open && (
            <>
              <motion.div
                key="user-backdrop"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                onClick={close}
                className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
                aria-hidden
              />

              <motion.div
                key="user-dropdown"
                ref={dropdownRef}
                role="menu"
                aria-label="User account menu"
                initial={{ opacity: 0, scale: 0.96, y: -6 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.96, y: -4 }}
                transition={{ type: "spring", stiffness: 500, damping: 30 }}
                style={{ top: dropPos.top, right: dropPos.right }}
                className={[
                  "fixed z-50 w-80 max-h-[min(32rem,calc(100vh-5rem))] overflow-y-auto",
                  "bg-[#0B0716]",
                  "rounded-xl",
                  "border border-purple-500/20",
                  "shadow-2xl shadow-purple-500/10",
                ].join(" ")}
              >
                <motion.div
                  className="absolute inset-x-4 top-0 h-px bg-gradient-to-r from-transparent via-purple-500/50 to-transparent"
                  aria-hidden
                />

                <div className="flex items-center gap-3 border-b border-white/10 p-4">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-purple-500 to-purple-700 text-sm font-semibold text-white">
                    {avatarText}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-white">{displayName}</p>
                    {userEmail ? (
                      <p className="mt-0.5 truncate text-xs text-gray-400" title={userEmail}>
                        {userEmail}
                      </p>
                    ) : null}
                  </div>
                  <span className="ml-auto shrink-0 rounded border border-purple-500/30 bg-purple-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-purple-300">
                    PRO
                  </span>
                </div>

                {/* Sign-in + linked data — from live API, not guessed */}
                <div className="border-b border-white/10 px-4 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-gray-500">
                    How you signed in
                  </p>
                  <div className="mt-2 flex items-start gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-2">
                    <Mail className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gray-400" aria-hidden />
                    <div>
                      <p className="text-xs font-medium text-white">Email & password</p>
                      <p className="mt-0.5 text-[10px] leading-relaxed text-gray-500">
                        Login is not via document upload. Bank/card data is linked separately below.
                      </p>
                    </div>
                  </div>

                  <p className="mt-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-gray-500">
                    Linked financial data
                  </p>

                  {sourcesLoading ? (
                    <p className="mt-2 text-xs text-gray-500">Loading linked accounts…</p>
                  ) : sourcesErr ? (
                    <p className="mt-2 rounded-lg border border-rose-500/25 bg-rose-500/10 px-2 py-1.5 text-[11px] text-rose-200">
                      {sourcesErr}
                    </p>
                  ) : sources.length > 0 ? (
                    <ul className="mt-2 space-y-1.5">
                      {sources.map((s) => (
                        <LinkedAccountRow key={s.id} source={s} />
                      ))}
                    </ul>
                  ) : profileBank ? (
                    <div className="mt-2 flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 px-2.5 py-2">
                      <Landmark className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-300" aria-hidden />
                      <div>
                        <p className="text-xs font-medium text-white">{formatInstitution(profileBank)}</p>
                        <p className="mt-0.5 text-[10px] text-gray-500">
                          Selected at signup · upload a statement in Settings to import transactions
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-2 flex items-start gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-2">
                      <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gray-500" aria-hidden />
                      <p className="text-[11px] leading-relaxed text-gray-500">
                        No bank or statement linked yet. Go to Settings → upload bank statement or add a card.
                      </p>
                    </div>
                  )}
                </div>

                <div className="p-2">
                  {MENU_ITEMS.map((item, idx) => {
                    if (item === null) {
                      return <div key={`divider-${idx}`} className="my-1 h-px bg-white/[0.07]" />;
                    }
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        role="menuitem"
                        onClick={() => handleItem(item)}
                        className={`group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/40 ${
                          item.danger
                            ? "text-gray-300 hover:bg-red-500/10 hover:text-red-400"
                            : "text-gray-300 hover:bg-white/5 hover:text-white"
                        }`}
                      >
                        <span
                          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors duration-150 ${
                            item.danger
                              ? "bg-white/[0.04] group-hover:bg-red-500/15"
                              : "bg-white/5 group-hover:bg-purple-500/20"
                          }`}
                        >
                          <Icon
                            size={15}
                            className={`transition-colors duration-150 ${
                              item.danger
                                ? "text-gray-400 group-hover:text-red-400"
                                : "text-gray-400 group-hover:text-purple-300"
                            }`}
                          />
                        </span>

                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium leading-none">{item.label}</p>
                          {item.description ? (
                            <p className="mt-0.5 text-xs leading-none text-gray-400 transition-colors group-hover:text-gray-300">
                              {item.description}
                            </p>
                          ) : null}
                        </div>

                        {item.external ? (
                          <ExternalLink
                            size={13}
                            className="ml-auto shrink-0 text-gray-600 transition-colors group-hover:text-gray-400"
                            aria-hidden
                          />
                        ) : null}
                      </button>
                    );
                  })}
                </div>

                <div className="border-t border-white/10 px-4 py-2.5">
                  <p className="text-center text-[10px] text-gray-500">
                    SmartSpend v2 · Protected by FraudShield AI
                  </p>
                </div>
              </motion.div>
            </>
          )}
        </AnimatePresence>,
        document.body
      )}
    </>
  );
};

export default UserMenu;
