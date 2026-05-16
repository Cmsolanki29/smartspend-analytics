import React, { useCallback, useEffect, useState } from "react";
import { Landmark, CreditCard, Eye, EyeOff, Plus } from "lucide-react";
import { getConnectedSources, toggleSourceVisibility, updateDashboardMode } from "../../services/api";
import { useAuth } from "../../context/AuthContext";

function iconForType(t) {
  if (t === "credit_card") return CreditCard;
  return Landmark;
}

/** Map API / DB dashboard_mode string to radio id used in this screen. */
function mapDashboardModeString(raw) {
  const s = String(raw || "merged").trim().toLowerCase();
  const map = {
    card_only: "credit_card_only",
    cards_only: "credit_card_only",
    cc_only: "credit_card_only",
    bank: "bank_only",
    merged_view: "merged",
    both: "merged",
  };
  return (
    map[s] ||
    (s.includes("card") ? "credit_card_only" : s.includes("bank") ? "bank_only" : s) ||
    "merged"
  );
}

function normalizeModeId(id) {
  const map = {
    card_only: "credit_card_only",
    bank_only: "bank_only",
    credit_card_only: "credit_card_only",
    merged: "merged",
  };
  return map[id] || id;
}

export default function ConnectedAccountsSettings({ userId, onGoUpload }) {
  const { reloadUser, user } = useAuth();
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [mode, setMode] = useState("merged");
  const [savingMode, setSavingMode] = useState(false);
  const [saveOk, setSaveOk] = useState(false);

  const load = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setErr("");
    try {
      const data = await getConnectedSources(userId);
      setSources(data.sources || []);
      if (data.dashboard_mode != null && String(data.dashboard_mode).trim() !== "") {
        setMode(normalizeModeId(mapDashboardModeString(data.dashboard_mode)));
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load accounts");
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    load();
  }, [load]);

  /* JWT /auth/me only describes the logged-in user. Workspace `userId` can be another demo user — do not overwrite mode from the wrong profile. */
  useEffect(() => {
    if (userId == null || user?.id == null || Number(userId) !== Number(user.id)) return;
    const m = user?.dashboard_mode;
    if (!m) return;
    setMode(normalizeModeId(mapDashboardModeString(m)));
  }, [user?.dashboard_mode, user?.id, userId]);

  const onToggleVisible = async (sourceId, next) => {
    const snapshot = sources.map((s) => ({ ...s }));
    setSources((rows) =>
      rows.map((s) => (s.id === sourceId ? { ...s, is_visible_on_dashboard: next } : s))
    );
    setErr("");
    try {
      await toggleSourceVisibility({ userId, sourceId, visible: next });
      await load();
      await reloadUser();
      // Notify all modules to re-fetch with updated account visibility
      try {
        window.dispatchEvent(new CustomEvent("dashboardModeChanged", { detail: { mode } }));
      } catch {
        /* ignore */
      }
    } catch (e) {
      setSources(snapshot);
      setErr(e instanceof Error ? e.message : "Update failed");
    }
  };

  const applyMode = async () => {
    setSavingMode(true);
    setErr("");
    setSaveOk(false);
    try {
      const visibleIds = sources.filter((s) => s.is_visible_on_dashboard).map((s) => s.id);
      const resp = await updateDashboardMode({ userId, mode, visibleSourceIds: visibleIds });
      const savedMode = resp?.mode ? normalizeModeId(mapDashboardModeString(resp.mode)) : mode;
      if (resp?.mode) setMode(savedMode);
      await reloadUser();
      await load();
      setSaveOk(true);
      window.setTimeout(() => setSaveOk(false), 3200);
      // Notify Dashboard + TransactionTable to re-fetch with the new mode
      try {
        window.dispatchEvent(new CustomEvent("dashboardModeChanged", { detail: { mode: savedMode } }));
      } catch {
        /* ignore */
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save dashboard mode");
    } finally {
      setSavingMode(false);
    }
  };

  return (
    <div className="rounded-2xl border border-white/10 bg-[#0c1022]/90 p-5 md:p-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="font-heading text-lg font-semibold text-white">Connected accounts</h2>
          <p className="mt-1 text-sm text-white/55">
            Toggle which sources feed your dashboard, then pick bank-only, card-only, or merged view.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onGoUpload?.("credit_card")}
            className="inline-flex items-center gap-2 rounded-xl border border-violet-500/40 bg-violet-500/15 px-3 py-2 text-sm font-semibold text-violet-100 hover:bg-violet-500/25"
          >
            <Plus className="h-4 w-4" aria-hidden />
            Add credit card
          </button>
          <button
            type="button"
            onClick={() => onGoUpload?.("bank_statement_pdf")}
            className="inline-flex items-center gap-2 rounded-xl border border-cyan-500/35 bg-cyan-500/10 px-3 py-2 text-sm font-semibold text-cyan-100 hover:bg-cyan-500/20"
          >
            <Plus className="h-4 w-4" aria-hidden />
            Upload bank statement
          </button>
        </div>
      </div>

      {err ? (
        <p className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">{err}</p>
      ) : null}
      {saveOk ? (
        <p className="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200">
          Dashboard view saved. Open Dashboard to see bank-only / card-only / merged data.
        </p>
      ) : null}

      {loading ? (
        <p className="mt-6 text-sm text-white/45">Loading accounts…</p>
      ) : sources.length === 0 ? (
        <p className="mt-6 text-sm text-white/50">
          No linked sources yet. Use the buttons above to upload a card or bank statement (demo seed data still appears
          in merged mode).
        </p>
      ) : (
        <ul className="mt-5 space-y-3">
          {sources.map((s) => {
            const Icon = iconForType(s.source_type);
            const vis = Boolean(s.is_visible_on_dashboard);
            return (
              <li
                key={s.id}
                className="flex flex-col gap-3 rounded-xl border border-white/10 bg-white/[0.04] p-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex min-w-0 items-start gap-3">
                  <span className="mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white/[0.06] text-white/90">
                    <Icon className="h-5 w-5" aria-hidden />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate font-medium text-white">{s.institution_name}</p>
                    <p className="text-xs text-white/45">
                      {String(s.source_type || "").replace(/_/g, " ")}
                      {s.account_number_masked ? ` · ${s.account_number_masked}` : ""}
                      {s.is_primary ? " · Primary" : ""}
                      {s.added_via ? ` · via ${s.added_via}` : ""}
                    </p>
                    <p className="mt-1 text-xs text-white/35">
                      {Number(s.transactions_count || 0)} transactions
                      {s.last_upload ? ` · last upload ${new Date(s.last_upload).toLocaleDateString("en-IN")}` : ""}
                    </p>
                  </div>
                </div>
                <label className="flex cursor-pointer items-center gap-2 text-sm text-white/80">
                  {vis ? <Eye className="h-4 w-4 text-emerald-300" /> : <EyeOff className="h-4 w-4 text-white/35" />}
                  <span>On dashboard</span>
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-violet-500"
                    checked={vis}
                    onChange={(e) => onToggleVisible(s.id, e.target.checked)}
                  />
                </label>
              </li>
            );
          })}
        </ul>
      )}

      {!loading && sources.length > 0 ? (
        <div className="mt-8 border-t border-white/10 pt-6">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-white/50">Dashboard view</h3>
          <p className="mt-1 text-xs text-white/40">Currently: {String(mode || "merged").replace(/_/g, " ")}</p>
          <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            {[
              { id: "bank_only", label: "Bank only" },
              { id: "credit_card_only", label: "Card only" },
              { id: "merged", label: "Both (merged)" },
            ].map((o) => (
              <label
                key={o.id}
                className={`flex cursor-pointer items-center gap-2 rounded-xl border px-4 py-3 text-sm font-medium transition ${
                  mode === o.id
                    ? "border-violet-500/60 bg-violet-500/15 text-white"
                    : "border-white/10 bg-white/[0.03] text-white/60 hover:border-white/20"
                }`}
              >
                <input
                  type="radio"
                  name="dash-mode"
                  className="accent-violet-500"
                  checked={mode === o.id}
                  onChange={() => setMode(normalizeModeId(o.id))}
                />
                {o.label}
              </label>
            ))}
          </div>
          <button
            type="button"
            disabled={savingMode}
            onClick={applyMode}
            className="mt-4 w-full rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 py-2.5 text-sm font-semibold text-white hover:from-violet-700 hover:to-indigo-700 disabled:opacity-50 sm:w-auto sm:px-8"
          >
            {savingMode ? "Saving…" : "Switch view"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
