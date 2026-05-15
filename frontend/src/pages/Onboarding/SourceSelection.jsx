import { useState } from "react";
import { getAccessToken } from "../../services/api";

const BANKS = [
  { id: "HDFC", name: "HDFC Bank", emoji: "🏦" },
  { id: "SBI", name: "State Bank of India", emoji: "🏛️" },
  { id: "ICICI", name: "ICICI Bank", emoji: "🏦" },
  { id: "Axis", name: "Axis Bank", emoji: "🏦" },
  { id: "Kotak", name: "Kotak Mahindra", emoji: "🏦" },
];

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

function extractMsg(data) {
  if (!data) return "Upload failed";
  const d = data.detail ?? data.error ?? data.message;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => e?.msg || JSON.stringify(e)).join("; ");
  if (d && typeof d === "object") return JSON.stringify(d);
  return "Upload failed";
}

async function apiUploadPDF({ userId, file, source_type, institution_name }) {
  const token = getAccessToken();
  const form = new FormData();
  form.append("file", file);
  form.append("user_id", String(userId));   // endpoint expects Form field, not query param
  form.append("source_type", source_type);
  form.append("institution_name", institution_name);

  const res = await fetch(`/api/documents/upload`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.success === false) {
    throw new Error(extractMsg(data));
  }
  return data;
}

export default function SourceSelection({ userId, onComplete }) {
  const [screen, setScreen] = useState("main"); // main | bank_picker | pdf_upload | success
  const [activeOption, setActiveOption] = useState(null);
  const [selectedBank, setSelectedBank] = useState(null);
  const [uploadFile, setUploadFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [successData, setSuccessData] = useState(null);
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

  async function handleBankLink() {
    if (!selectedBank) { setError("Please select a bank first"); return; }
    setBusy(true);
    clearError();
    try {
      await apiSetMode({
        userId,
        dashboard_mode: "bank_only",
        bank_name: selectedBank,
        onboarding_source: "bank",
      });
      onComplete();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handlePDFUpload() {
    if (!uploadFile) { setError("Please choose a file first"); return; }
    setBusy(true);
    clearError();
    try {
      const isCard = activeOption === "credit_card";
      const data = await apiUploadPDF({
        userId,
        file: uploadFile,
        source_type: isCard ? "credit_card" : "bank_statement_pdf",
        institution_name: isCard ? "Credit Card" : "Bank Statement",
      });
      await apiSetMode({
        userId,
        dashboard_mode: isCard ? "credit_card_only" : "bank_only",
        onboarding_source: isCard ? "credit_card" : "bank_statement",
      });
      setSuccessData({ imported: data.imported ?? 0, duplicates: data.duplicates ?? 0 });
      setScreen("success");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  // ── Success ───────────────────────────────────────────────────────────────
  if (screen === "success") {
    const total = (successData?.imported ?? 0) + (successData?.duplicates ?? 0);
    const allDupes = successData?.imported === 0 && successData?.duplicates > 0;
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[#070418] px-4 text-center">
        <div className="mx-auto w-full max-w-md rounded-2xl border border-white/10 bg-white/[0.04] p-8 backdrop-blur-xl">
          <div className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-full bg-emerald-500/15 text-5xl">
            ✅
          </div>
          <h2 className="text-2xl font-bold text-white">
            {allDupes ? "Statement Connected!" : "Successfully Imported!"}
          </h2>
          <div className="mt-4 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-6 py-4">
            {allDupes ? (
              <p className="text-base text-emerald-300">
                ✓ {total} transactions found — already up to date
              </p>
            ) : (
              <p className="text-base text-emerald-300">
                ✓ {successData?.imported} transactions imported
              </p>
            )}
            {!allDupes && successData?.duplicates > 0 && (
              <p className="mt-1 text-sm text-slate-400">
                {successData.duplicates} duplicates skipped
              </p>
            )}
          </div>
          <p className="mt-4 text-sm text-slate-400">Your financial insights are ready.</p>
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

  // ── Bank Picker ───────────────────────────────────────────────────────────
  if (screen === "bank_picker") {
    return (
      <PageShell>
        <BackBtn onClick={() => { setScreen("main"); clearError(); setSelectedBank(null); }} />
        <h2 className="mb-1 text-2xl font-bold text-white">Select Your Bank</h2>
        <p className="mb-6 text-sm text-slate-400">Choose your primary bank account</p>
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
          onClick={handleBankLink}
          disabled={!selectedBank || busy}
          className="mt-5 w-full max-w-sm rounded-xl bg-gradient-to-r from-violet-600 via-fuchsia-600 to-pink-600 py-3 text-base font-semibold text-white transition hover:opacity-90 disabled:opacity-40"
        >
          {busy ? "Linking…" : "Link Bank & Continue →"}
        </button>
        <SkipBtn onClick={handleSkip} busy={busy} />
      </PageShell>
    );
  }

  // ── PDF Upload ────────────────────────────────────────────────────────────
  if (screen === "pdf_upload") {
    const isCard = activeOption === "credit_card";
    return (
      <PageShell>
        <BackBtn
          onClick={() => {
            setScreen("main");
            clearError();
            setUploadFile(null);
          }}
        />
        <h2 className="mb-1 text-2xl font-bold text-white">
          {isCard ? "💳 Add Credit Card" : "📄 Upload Bank Statement"}
        </h2>
        <p className="mb-6 text-sm text-slate-400">
          {isCard
            ? "Upload your credit card PDF statement"
            : "Import transactions from PDF or CSV"}
        </p>
        <label
          htmlFor="ss-file-input"
          className={`flex w-full max-w-sm cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-sm transition ${
            uploadFile
              ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-300"
              : "border-white/15 bg-white/[0.03] text-slate-400 hover:border-violet-500/50 hover:text-slate-200"
          }`}
        >
          <span className="text-3xl">{uploadFile ? "✓" : "📂"}</span>
          {uploadFile ? uploadFile.name : "Click to choose file (PDF, CSV — max 20 MB)"}
        </label>
        <input
          id="ss-file-input"
          type="file"
          accept=".pdf,.csv,.xlsx"
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
          disabled={!uploadFile || busy}
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
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#070418] px-4 py-12">
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
            desc="Full tracking — salary, EMIs, expenses"
            badge="Recommended"
            onClick={() => { setActiveOption("bank"); setScreen("bank_picker"); }}
          />
          <OptionCard
            icon="💳"
            title="Add Credit Card"
            desc="Spending insights from card statement"
            onClick={() => { setActiveOption("credit_card"); setScreen("pdf_upload"); }}
          />
          <OptionCard
            icon="📄"
            title="Upload Bank Statement"
            desc="Import transactions from PDF or CSV"
            onClick={() => { setActiveOption("bank_statement"); setScreen("pdf_upload"); }}
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

function PageShell({ children }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#070418] px-4 py-12">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -left-32 top-0 h-96 w-96 rounded-full bg-violet-600/20 blur-[120px]" />
        <div className="absolute -right-20 bottom-0 h-80 w-80 rounded-full bg-cyan-500/15 blur-[100px]" />
      </div>
      <div className="relative z-10 flex w-full max-w-md flex-col items-center">
        {children}
      </div>
    </div>
  );
}

function BackBtn({ onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mb-6 self-start rounded-lg border border-white/10 px-3 py-1.5 text-sm text-violet-400 transition hover:border-violet-500/50 hover:text-violet-200"
    >
      ← Back
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
