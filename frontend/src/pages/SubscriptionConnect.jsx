import React, { useState } from "react";
import { Link2, TrendingUp, Zap } from "lucide-react";
import AppSelectionModal from "../components/Subscriptions/AppSelectionModal";
import PermissionModal from "../components/Subscriptions/PermissionModal";
import { GlassCard } from "../components/intro/GlassCard";
import { setSubscriptionFlowConnected } from "../utils/subscriptionFlowStorage";
import { useToast } from "../components/common/Toast";
import { syncLinkedAppsToBackend } from "../services/subscriptionDeviceSync";

/**
 * Step 1 — device link + connect flow (first-time users).
 * @param {object} props
 * @param {number} props.ownerId — JWT user id (must match API `/subscription-intelligence/{id}`)
 * @param {() => void} props.onComplete — after permissions granted + apps saved (hub opens immediately)
 */
export default function SubscriptionConnect({ ownerId, onComplete }) {
  const { showToast } = useToast();
  const [showApps, setShowApps] = useState(false);
  const [showPerm, setShowPerm] = useState(false);
  const [selectedIds, setSelectedIds] = useState([]);
  const [syncing, setSyncing] = useState(false);

  const handleAllow = async () => {
    if (!ownerId) {
      showToast("You must be signed in to connect apps.", "error");
      return;
    }
    const ids = [...selectedIds];
    if (ids.length === 0) {
      showToast("Select at least one app, then try again.", "error");
      return;
    }

    setSubscriptionFlowConnected(ownerId, ids);
    setShowPerm(false);
    setShowApps(false);
    setSelectedIds([]);
    onComplete();

    setSyncing(true);
    try {
      const res = await syncLinkedAppsToBackend(ownerId, ids);
      if (res?.ok) {
        showToast("Applications connected — intelligence data synced.", "success");
      } else if (res?.reason === "bad_user") {
        showToast("Your account id is missing. Sign in again, then retry.", "error");
      } else {
        showToast("Apps saved. Server sync will complete when the API is ready.", "info");
      }
    } catch {
      showToast("Apps linked on this device. Hub is ready — sync retries in the background.", "info");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-[calc(100vh-8rem)] max-w-4xl flex-col items-center justify-center px-4 py-10">
      <GlassCard padding="lg" surface="panel" className="relative w-full overflow-hidden border-cyan-500/25">
        <div
          className="pointer-events-none absolute -right-32 -top-32 h-72 w-72 rounded-full bg-cyan-500/10 blur-3xl"
          aria-hidden
        />
        <div className="relative text-center">
          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-500 to-violet-600 shadow-lg shadow-cyan-500/25">
            <Link2 className="h-8 w-8 text-white" aria-hidden />
          </div>

          <p className="mb-2 inline-flex rounded-full border border-cyan-400/30 bg-cyan-500/10 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-cyan-200">
            Device link
          </p>

          <h1 className="font-heading text-3xl font-bold text-white sm:text-4xl">Unlock 10× smarter detection</h1>
          <h2 className="mt-2 font-heading text-xl font-semibold text-gray-300 sm:text-2xl">Link your subscriptions.</h2>

          <p className="mx-auto mt-5 max-w-xl text-sm leading-relaxed text-gray-400 sm:text-base">
            We infer subscription value from usage minutes, sessions, and peaks — tuned for your wallet. Connect the apps
            you use so the AI Analysis Engine and Smart Reminder Engine can go to work.
          </p>

          <button
            type="button"
            disabled={syncing}
            onClick={() => setShowApps(true)}
            className="mt-8 inline-flex items-center gap-3 rounded-2xl bg-gradient-to-r from-cyan-500 to-violet-600 px-10 py-4 text-base font-bold text-white shadow-xl shadow-cyan-500/25 transition hover:brightness-110 disabled:opacity-60"
          >
            <Zap className="h-5 w-5" aria-hidden />
            {syncing ? "Syncing intelligence…" : "Connect your subscriptions"}
            <TrendingUp className="h-5 w-5" aria-hidden />
          </button>

          <div className="mt-10 grid gap-4 text-left sm:grid-cols-3 sm:text-center">
            <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
              <p className="text-xs font-semibold text-cyan-300">AI analysis</p>
              <p className="mt-1 text-xs text-gray-400">Verdicts, migrations, savings signals</p>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
              <p className="text-xs font-semibold text-violet-300">Smart reminders</p>
              <p className="mt-1 text-xs text-gray-400">Renewals, snooze with accountability</p>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
              <p className="text-xs font-semibold text-amber-300">Waste detection</p>
              <p className="mt-1 text-xs text-gray-400">Dormant subs & value leakage</p>
            </div>
          </div>
        </div>
      </GlassCard>

      <AppSelectionModal
        open={showApps}
        variant="initial"
        onClose={() => setShowApps(false)}
        onConfirm={(ids) => {
          if (!ids?.length) {
            showToast("Select at least one app to continue.", "error");
            return;
          }
          setSelectedIds(ids);
          setShowApps(false);
          setShowPerm(true);
        }}
      />

      <PermissionModal
        open={showPerm}
        appIds={selectedIds}
        onDeny={() => {
          setShowPerm(false);
          setSelectedIds([]);
        }}
        onAllow={() => {
          void handleAllow();
        }}
      />
    </div>
  );
}
