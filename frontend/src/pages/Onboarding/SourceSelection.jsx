import { useState } from "react";
import { getAccessToken } from "../../services/api";
import UploadResultSummary from "../../components/Upload/UploadResultSummary";
import {
  UPLOAD_ACCEPT,
  UPLOAD_HINT,
  uploadFinancialDocument,
} from "../../services/documentUpload";
import { dispatchDataUpdated } from "../../utils/refetchAll";

const BANKS = [
  { id: "HDFC", name: "HDFC Bank", emoji: "🏦" },
  { id: "SBI", name: "State Bank of India", emoji: "🏛️" },
  { id: "ICICI", name: "ICICI Bank", emoji: "🏦" },
  { id: "AXIS", name: "Axis Bank", emoji: "🏦" },
  { id: "KOTAK", name: "Kotak Mahindra", emoji: "🏦" },
  { id: "PNB", name: "Punjab National Bank", emoji: "🏛️" },
  { id: "BOB", name: "Bank of Baroda", emoji: "🏦" },
];

async function apiLinkBankDemo({ bankSlug, bankName, accountLast4 }) {
  const token = getAccessToken();
  const res = await fetch(`/api/onboarding/link-bank-demo`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      bank_slug: bankSlug,
      bank_name: bankName || undefined,
      account_last4: accountLast4 || undefined,
    }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || d.message || "Could not link bank");
  }
  return res.json();
}

async function apiSetMode({ userId, dashboard_mode, bank_name, onboarding_source }) {
  const token = getAccessToken();
  const res = await fetch(`/api/user/set-dashboard-mode`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      user_id: userId,
      dashboard_mode,
      bank_name: bank_name || undefined,
      onboarding_source,
    }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || d.message || "Setup failed");
  }
  return res.json();
}

export default function SourceSelection({ userId, userDisplayName, onComplete, onBack }) {
  const [screen, setScreen] = useState("main"); // main | bank_picker | bank_linked | pdf_upload | success
  const [activeOption, setActiveOption] = useState(null);
  const [selectedBank, setSelectedBank] = useState(null);
  const [uploadFile, setUploadFile] = useState(null);
  const [institutionName, setInstitutionName] = useState("");
  const [accountLast4, setAccountLast4] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [bankLinkResult, setBankLinkResult] = useState(null);
  const [error, setError] = useState("");

  const clearError = () => setError("");

  async function handleSkip() {
    setBusy(true);
    clearError();
    try {
      await apiSetMode({ userId, dashboard_mode: "bank_only", onboarding_source: "skipped" });
      onComplete();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleBankLinkDemo() {
    if (!selectedBank) {
      setError("Please select a bank first");
      return;
    }
    setBusy(true);
    clearError();
    try {
      const bank = BANKS.find((b) => b.id === selectedBank);
      const data = await apiLinkBankDemo({
        bankSlug: selectedBank,
        bankName: bank?.name || selectedBank,
        accountLast4: accountLast4.trim() || undefined,
      });
      setInstitutionName(bank?.name || data.bank_name || selectedBank);
      setBankLinkResult(data);
      setScreen("bank_linked");
      const sy = Number(data?.statement_year);
      const sm = Number(data?.statement_month);
      if (sy > 0 && sm >= 1 && sm <= 12) {
        window.dispatchEvent(
          new CustomEvent("smartspend:set-view-month", {
            detail: { year: sy, month: sm, user_id: Number(userId) },
          })
        );
      }
      dispatchDataUpdated({
        userId,
        sourceName: data.bank_name,
        month: sm >= 1 && sm <= 12 ? sm : undefined,
        year: sy > 0 ? sy : undefined,
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function handleBankContinueToUpload() {
    if (!selectedBank) {
      setError("Please select a bank first");
      return;
    }
    const bank = BANKS.find((b) => b.id === selectedBank);
    setInstitutionName(bank?.name || selectedBank);
    setActiveOption("bank_statement");
    setScreen("pdf_upload");
    clearError();
  }

  async function handlePDFUpload() {
    if (!uploadFile) { setError("Please choose a file first"); return; }
    if (!institutionName.trim()) { setError("Enter your bank or card name"); return; }
    setBusy(true);
    clearError();
    try {
      const isCard = activeOption === "credit_card";
      const data = await uploadFinancialDocument({
        file: uploadFile,
        userId,
        sourceType: isCard ? "credit_card" : "bank_statement_pdf",
        institutionName: institutionName.trim(),
        accountNumberMasked: accountLast4.trim() || undefined,
        addedVia: "onboarding_upload",
        apiBase: "/api",
      });
      const imported = Number(data?.imported ?? data?.transactions_stored ?? 0);
      const extracted = Number(data?.extracted ?? data?.transactions_extracted ?? 0);
      if (imported === 0 && extracted === 0) {
        throw new Error(
          "We could not find transactions in this file. Try a PDF or CSV export from your bank app."
        );
      }
      await apiSetMode({
        userId,
        dashboard_mode: "merged",
        onboarding_source: isCard ? "credit_card" : "bank_statement",
      });
      setUploadResult(data);
      setScreen("success");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  // ── Success ───────────────────────────────────────────────────────────────
  if (screen === "success") {
    const imported = uploadResult?.imported ?? uploadResult?.transactions_stored ?? 0;
    const allDupes = imported === 0 && (uploadResult?.duplicates ?? 0) > 0;
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[#070418] px-4 text-center">
        <div className="mx-auto w-full max-w-md rounded-2xl border border-white/10 bg-white/[0.04] p-8 backdrop-blur-xl">
          <div className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-full bg-emerald-500/15 text-5xl">
            ✅
          </div>
          <h2 className="text-2xl font-bold text-white">
            {allDupes ? "Statement Connected!" : "Successfully Imported!"}
          </h2>
          <div className="mt-4">
            <UploadResultSummary result={uploadResult} variant="signup" />
          </div>
          <p className="mt-4 text-sm text-slate-400">
            {imported > 0 && uploadResult?.statement_month
              ? `Dashboard will open on ${uploadResult.statement_month}/${uploadResult.statement_year}.`
              : imported > 0
                ? "Dashboard will show your latest statement month."
                : "Connected — add another statement in Settings if needed."}
          </p>
          <button
            type="button"
            onClick={onComplete}
            className="mt-6 w-full rounded-xl bg-gradient-to-r from-violet-600 via-fuchsia-600 to-pink-600 py-3 text-base font-semibold text-white transition hover:opacity-90"
          >
            Go to Dashboard →
          </button>
        </div>
      </div>
    );
  }

  // ── Bank linked (ghost pool preview) ─────────────────────────────────────
  if (screen === "bank_linked" && bankLinkResult) {
    const preview = bankLinkResult.preview || [];
    const label = userDisplayName || bankLinkResult.display_name || "You";
    return (
      <PageShell
        onBack={() => {
          setScreen("bank_picker");
          clearError();
        }}
      >
        <h2 className="mb-1 text-2xl font-bold text-white">Account linked</h2>
        <p className="mb-4 max-w-sm text-sm text-slate-400">
          Your <span className="text-violet-300">{bankLinkResult.bank_name}</span> account is linked to{" "}
          <span className="text-violet-300">{label}</span>. These are your recent transactions.
        </p>
        <div className="w-full max-w-md overflow-hidden rounded-xl border border-white/10 bg-white/[0.04]">
          <div className="border-b border-white/10 px-4 py-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            Recent transactions
          </div>
          <ul className="max-h-64 divide-y divide-white/5 overflow-y-auto text-left text-sm">
            {preview.length === 0 ? (
              <li className="px-4 py-6 text-center text-slate-500">Loading preview…</li>
            ) : (
              preview.map((tx, i) => (
                <li key={`${tx.date}-${tx.merchant}-${i}`} className="flex items-center justify-between gap-2 px-4 py-2.5">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-white">{tx.merchant}</p>
                    <p className="text-xs text-slate-500">{tx.date} · {tx.category}</p>
                  </div>
                  <span
                    className={
                      tx.type === "CREDIT"
                        ? "shrink-0 font-semibold text-emerald-400"
                        : "shrink-0 font-semibold text-slate-200"
                    }
                  >
                    {tx.type === "CREDIT" ? "+" : "−"}₹{Number(tx.amount).toLocaleString("en-IN")}
                  </span>
                </li>
              ))
            )}
          </ul>
        </div>
        <p className="mt-3 max-w-sm text-xs text-slate-500">
          {bankLinkResult.total_transactions} transactions synced to your account
          {bankLinkResult.workspace?.emi_count != null
            ? ` · ${bankLinkResult.workspace.emi_count} EMI(s) · ${bankLinkResult.workspace.fraud_count ?? 0} fraud alert(s)`
            : ""}
        </p>
        {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
        <button
          type="button"
          onClick={async () => {
            setBusy(true);
            try {
              await apiSetMode({
                userId,
                dashboard_mode: "bank_only",
                bank_name: institutionName,
                onboarding_source: "bank_ghost_link",
              });
              onComplete();
            } catch (e) {
              setError(e.message);
            } finally {
              setBusy(false);
            }
          }}
          disabled={busy}
          className="mt-5 w-full max-w-sm rounded-xl bg-gradient-to-r from-violet-600 via-fuchsia-600 to-pink-600 py-3 text-base font-semibold text-white transition hover:opacity-90 disabled:opacity-40"
        >
          {busy ? "Opening dashboard…" : "Go to Dashboard →"}
        </button>
        <button
          type="button"
          onClick={handleBankContinueToUpload}
          className="mt-3 text-sm text-violet-300 underline-offset-2 hover:underline"
        >
          Upload real statement (optional)
        </button>
      </PageShell>
    );
  }

  // ── Bank Picker ───────────────────────────────────────────────────────────
  if (screen === "bank_picker") {
    return (
      <PageShell
        onBack={() => {
          setScreen("main");
          clearError();
          setSelectedBank(null);
        }}
      >
        <h2 className="mb-1 text-2xl font-bold text-white">Select Your Bank</h2>
        <p className="mb-6 text-sm text-slate-400">
          Pick any bank — we link realistic day-to-day spends under that account name.
        </p>
        <div className="grid w-full max-w-sm grid-cols-2 gap-3">
          {BANKS.map((b) => (
            <button
              key={b.id}
              type="button"
              onClick={() => setSelectedBank(b.id)}
              className={`flex flex-col items-center gap-1 rounded-xl border-2 px-4 py-4 text-center text-sm font-medium transition ${
                selectedBank === b.id
                  ? "border-violet-500 bg-violet-500/15 text-violet-200"
                  : "border-white/10 bg-white/[0.04] text-slate-300 hover:border-violet-500/50"
              }`}
            >
              <span className="text-2xl">{b.emoji}</span>
              {b.name}
            </button>
          ))}
        </div>
        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
        <button
          type="button"
          onClick={handleBankLinkDemo}
          disabled={!selectedBank || busy}
          className="mt-5 w-full max-w-sm rounded-xl bg-gradient-to-r from-violet-600 via-fuchsia-600 to-pink-600 py-3 text-base font-semibold text-white transition hover:opacity-90 disabled:opacity-40"
        >
          {busy ? "Linking account…" : "Link my bank account →"}
        </button>
        <button
          type="button"
          onClick={handleBankContinueToUpload}
          disabled={!selectedBank || busy}
          className="mt-3 w-full max-w-sm rounded-xl border border-white/15 py-2.5 text-sm font-medium text-slate-300 transition hover:border-violet-500/40"
        >
          Upload statement instead
        </button>
        <SkipBtn onClick={handleSkip} busy={busy} />
      </PageShell>
    );
  }

  // ── PDF Upload ────────────────────────────────────────────────────────────
  if (screen === "pdf_upload") {
    const isCard = activeOption === "credit_card";
    return (
      <PageShell
        onBack={() => {
          setScreen("main");
          clearError();
          setUploadFile(null);
        }}
      >
        <h2 className="mb-1 text-2xl font-bold text-white">
          {isCard ? "💳 Add Credit Card" : "📄 Upload Bank Statement"}
        </h2>
        <p className="mb-4 text-sm text-slate-400">
          {isCard
            ? "Upload your credit card statement (PDF, CSV, Excel, or photo)"
            : "Import transactions from PDF, CSV, Excel, or image"}
        </p>

        <div className="mb-3 w-full max-w-sm space-y-3">
          <div>
            <label className="mb-1 block text-left text-xs text-slate-400">
              {isCard ? "Credit card name" : "Bank name"}
            </label>
            <input
              value={institutionName}
              onChange={(e) => setInstitutionName(e.target.value)}
              placeholder={isCard ? "e.g. Axis Bank Credit Card" : "e.g. HDFC Bank savings"}
              className="w-full rounded-xl border border-white/10 bg-white/[0.06] px-4 py-2.5 text-sm text-white placeholder-white/30"
            />
          </div>
          <div>
            <label className="mb-1 block text-left text-xs text-slate-400">
              Last 4 digits <span className="text-slate-500">(optional)</span>
            </label>
            <input
              value={accountLast4}
              onChange={(e) => setAccountLast4(e.target.value)}
              placeholder="e.g. 4812"
              maxLength={8}
              className="w-full rounded-xl border border-white/10 bg-white/[0.06] px-4 py-2.5 text-sm text-white placeholder-white/30"
            />
          </div>
        </div>

        <label
          htmlFor="ss-file-input"
          className={`flex w-full max-w-sm cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-sm transition ${
            uploadFile
              ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-300"
              : "border-white/15 bg-white/[0.03] text-slate-400 hover:border-violet-500/50 hover:text-slate-200"
          }`}
        >
          <span className="text-3xl">{uploadFile ? "✓" : "📂"}</span>
          {uploadFile ? uploadFile.name : `Click to choose file (${UPLOAD_HINT})`}
        </label>
        <input
          id="ss-file-input"
          type="file"
          accept={UPLOAD_ACCEPT}
          className="hidden"
          onChange={(e) => {
            setUploadFile(e.target.files?.[0] || null);
            clearError();
          }}
        />
        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
        <button
          type="button"
          onClick={handlePDFUpload}
          disabled={!uploadFile || !institutionName.trim() || busy}
          className="mt-5 w-full max-w-sm rounded-xl bg-gradient-to-r from-violet-600 via-fuchsia-600 to-pink-600 py-3 text-base font-semibold text-white transition hover:opacity-90 disabled:opacity-40"
        >
          {busy ? "Processing… (this may take 30–60 s)" : "Upload & Extract Transactions →"}
        </button>
        <SkipBtn onClick={handleSkip} busy={busy} />
      </PageShell>
    );
  }

  // ── Main screen ───────────────────────────────────────────────────────────
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-[#070418] px-4 py-12">
      {onBack ? <FixedBackBtn onClick={onBack} /> : null}
      {/* Background blobs */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -left-32 top-0 h-96 w-96 rounded-full bg-violet-600/20 blur-[120px]" />
        <div className="absolute -right-20 bottom-0 h-80 w-80 rounded-full bg-cyan-500/15 blur-[100px]" />
      </div>
      <div className="relative z-10 w-full max-w-2xl text-center">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-cyan-400/90">
          Almost there
        </p>
        <h1 className="mb-2 text-3xl font-bold text-white md:text-4xl">
          Connect Your Accounts
        </h1>
        <p className="mb-10 text-slate-400">Choose how you want to track your finances</p>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <OptionCard
            icon="🏦"
            title="Link Bank Account"
            desc="Pick your bank, then upload a statement (PDF/CSV)"
            badge="Recommended"
            onClick={() => { setActiveOption("bank"); setScreen("bank_picker"); }}
          />
          <OptionCard
            icon="💳"
            title="Add Credit Card"
            desc="Spending insights from card statement"
            onClick={() => {
              setActiveOption("credit_card");
              setInstitutionName("");
              setScreen("pdf_upload");
            }}
          />
          <OptionCard
            icon="📄"
            title="Upload Bank Statement"
            desc="Import transactions from PDF or CSV"
            onClick={() => {
              setActiveOption("bank_statement");
              setInstitutionName("");
              setScreen("pdf_upload");
            }}
          />
        </div>

        {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

        <button
          type="button"
          onClick={handleSkip}
          disabled={busy}
          className="mt-8 rounded-xl border border-white/10 px-6 py-2.5 text-sm text-slate-400 transition hover:border-white/20 hover:text-slate-200 disabled:opacity-40"
        >
          {busy ? "Setting up…" : "Skip for now →"}
        </button>
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function PageShell({ children, onBack }) {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-[#070418] px-4 py-12">
      {onBack ? <FixedBackBtn onClick={onBack} /> : null}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -left-32 top-0 h-96 w-96 rounded-full bg-violet-600/20 blur-[120px]" />
        <div className="absolute -right-20 bottom-0 h-80 w-80 rounded-full bg-cyan-500/15 blur-[100px]" />
      </div>
      <div className="relative z-10 flex w-full max-w-md flex-col items-center pt-12">
        {children}
      </div>
    </div>
  );
}

function FixedBackBtn({ onClick, label = "← Back" }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Go back"
      className="fixed left-4 top-4 z-50 inline-flex items-center gap-1.5 rounded-xl border border-white/15 bg-[#0c1022]/90 px-4 py-2 text-sm font-medium text-slate-200 shadow-lg backdrop-blur-md transition hover:border-violet-500/50 hover:bg-white/[0.08] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/50"
    >
      {label}
    </button>
  );
}

function SkipBtn({ onClick, busy }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className="mt-4 text-sm text-slate-500 transition hover:text-slate-300 disabled:opacity-40"
    >
      Skip for now
    </button>
  );
}

function OptionCard({ icon, title, desc, badge, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group relative flex flex-col items-center rounded-2xl border-2 border-white/10 bg-white/[0.04] px-5 py-7 text-center transition hover:border-violet-500/60 hover:bg-violet-500/[0.07] hover:shadow-[0_0_32px_rgba(124,58,237,0.18)]"
    >
      <span className="mb-3 text-4xl">{icon}</span>
      <h3 className="mb-1 text-base font-semibold text-white">{title}</h3>
      <p className="text-sm leading-relaxed text-slate-400">{desc}</p>
      {badge && (
        <span className="mt-3 inline-block rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-0.5 text-xs font-semibold text-emerald-300">
          {badge}
        </span>
      )}
    </button>
  );
}
