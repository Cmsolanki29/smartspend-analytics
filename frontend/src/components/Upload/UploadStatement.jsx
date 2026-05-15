import React, { useState, useEffect, useRef } from "react";
import { getApiBaseUrl } from "../../services/apiBaseUrl";

const SOURCE_TYPES = [
  { id: "credit_card", label: "Credit Card", icon: "💳" },
  { id: "bank_statement_pdf", label: "Bank statement (PDF/CSV)", icon: "🏦" },
  { id: "upi", label: "UPI / GPay", icon: "📱" },
  { id: "other", label: "Other", icon: "📄" },
];

function Badge({ status }) {
  const map = {
    completed:  "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
    failed:     "bg-red-500/20 text-red-300 border-red-500/30",
    processing: "bg-amber-500/20 text-amber-300 border-amber-500/30",
    pending:    "bg-slate-500/20 text-slate-300 border-slate-500/30",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${map[status] ?? map.pending}`}>
      {status}
    </span>
  );
}

export default function UploadStatement({ userId, initialSourceType }) {
  const API = getApiBaseUrl();
  const [sourceType, setSourceType]   = useState(initialSourceType || "credit_card");
  const [bankName, setBankName]       = useState("");
  const [accountNo, setAccountNo]     = useState("");
  const [file, setFile]               = useState(null);
  const [uploading, setUploading]     = useState(false);
  const [result, setResult]           = useState(null);
  const [error, setError]             = useState(null);
  const [history, setHistory]         = useState([]);
  const [sources, setSources]         = useState([]);
  const [tab, setTab]                 = useState("upload"); // 'upload' | 'history' | 'sources'
  const fileRef = useRef(null);

  const loadHistory = () =>
    fetch(`${API}/documents/history?user_id=${userId}`)
      .then((r) => r.json())
      .then((d) => setHistory(d.uploads || []))
      .catch(() => {});

  const loadSources = () =>
    fetch(`${API}/sources/connected?user_id=${userId}`)
      .then((r) => r.json())
      .then((d) => setSources(d.sources || []))
      .catch(() => {});

  useEffect(() => {
    if (!userId) return;
    loadHistory();
    loadSources();
  }, [userId]);

  useEffect(() => {
    if (initialSourceType) setSourceType(initialSourceType);
  }, [initialSourceType]);

  const handleUpload = async () => {
    if (!file || !bankName.trim()) return;
    setUploading(true);
    setResult(null);
    setError(null);

    const form = new FormData();
    form.append("file", file);
    form.append("user_id", userId);
    form.append("source_type", sourceType);
    form.append("institution_name", bankName.trim());
    if (accountNo.trim()) form.append("account_number_masked", accountNo.trim());

    try {
      const res = await fetch(`${API}/documents/upload`, { method: "POST", body: form });
      let data;
      try {
        data = await res.json();
      } catch {
        throw new Error("Server returned a non-JSON response. Is the API running on the proxy port?");
      }
      if (!res.ok) throw new Error(data.detail || data.message || "Upload failed");
      if (data && data.success === false) {
        const msg = data.error || data.detail || "Upload saved but extraction failed.";
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      setResult(data);
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      loadHistory();
      loadSources();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Tabs */}
      <div className="flex gap-2 rounded-xl border border-white/10 bg-white/[0.04] p-1">
        {[
          { id: "upload",  label: "Upload Statement" },
          { id: "history", label: `Upload History (${history.length})` },
          { id: "sources", label: `Connected Sources (${sources.length})` },
        ].map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`flex-1 rounded-lg py-2 text-sm font-semibold transition ${
              tab === t.id
                ? "bg-violet-600 text-white"
                : "text-white/50 hover:text-white/80"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── UPLOAD PANEL ─────────────────────────────────────────────── */}
      {tab === "upload" && (
        <div className="rounded-2xl border border-white/10 bg-[#111827] p-6 space-y-5">
          <h3 className="text-lg font-bold text-white">Upload Bank / Card Statement</h3>

          {/* Source type buttons */}
          <div>
            <label className="mb-2 block text-sm text-white/60">What are you uploading?</label>
            <div className="flex flex-wrap gap-2">
              {SOURCE_TYPES.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setSourceType(s.id)}
                  className={`flex items-center gap-2 rounded-xl border px-4 py-2 text-sm font-semibold transition ${
                    sourceType === s.id
                      ? "border-violet-500 bg-violet-600/30 text-white"
                      : "border-white/10 bg-white/[0.04] text-white/50 hover:border-white/20 hover:text-white/80"
                  }`}
                >
                  <span>{s.icon}</span>
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* Institution name */}
          <div>
            <label className="mb-1 block text-sm text-white/60">
              {sourceType === "credit_card"
                ? "Credit Card Name"
                : sourceType === "upi"
                  ? "UPI App"
                  : "Institution name"}
            </label>
            <input
              value={bankName}
              onChange={(e) => setBankName(e.target.value)}
              placeholder={
                sourceType === "credit_card"
                  ? "e.g. HDFC Regalia Credit Card"
                  : sourceType === "upi"
                    ? "e.g. Google Pay / PhonePe"
                    : sourceType === "bank_statement_pdf"
                      ? "e.g. HDFC Bank savings"
                      : "e.g. HDFC Bank"
              }
              className="w-full rounded-xl border border-white/10 bg-white/[0.06] px-4 py-2.5 text-sm text-white placeholder-white/30 focus:border-violet-500/50 focus:outline-none"
            />
          </div>

          {/* Account number (optional) */}
          <div>
            <label className="mb-1 block text-sm text-white/60">
              Last 4 digits of account / card <span className="text-white/30">(optional)</span>
            </label>
            <input
              value={accountNo}
              onChange={(e) => setAccountNo(e.target.value)}
              placeholder="e.g. 4521"
              maxLength={8}
              className="w-full rounded-xl border border-white/10 bg-white/[0.06] px-4 py-2.5 text-sm text-white placeholder-white/30 focus:border-violet-500/50 focus:outline-none"
            />
          </div>

          {/* File input */}
          <div>
            <label className="mb-1 block text-sm text-white/60">Upload File</label>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.csv,.xlsx,.xls,.txt"
              onChange={(e) => setFile(e.target.files[0] || null)}
              className="w-full cursor-pointer rounded-xl border border-dashed border-white/20 bg-white/[0.04] px-4 py-3 text-sm text-white/70 file:mr-3 file:rounded-lg file:border-0 file:bg-violet-600/40 file:px-3 file:py-1 file:text-xs file:font-semibold file:text-white hover:border-violet-500/50"
            />
            <p className="mt-1 text-xs text-white/30">Supports PDF, CSV, Excel — max 20 MB</p>
            {file && (
              <p className="mt-1 text-xs text-emerald-400">
                ✓ {file.name} ({(file.size / 1024).toFixed(1)} KB)
              </p>
            )}
          </div>

          {/* Upload button */}
          <button
            type="button"
            onClick={handleUpload}
            disabled={uploading || !file || !bankName.trim()}
            className="w-full rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 py-3 text-sm font-bold text-white transition hover:from-violet-700 hover:to-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {uploading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                AI is extracting transactions…
              </span>
            ) : (
              "Upload & Extract Transactions"
            )}
          </button>
          {!file || !bankName.trim() ? (
            <p className="text-center text-xs text-white/35">
              {!bankName.trim()
                ? "Enter a card or bank name, then choose a PDF/CSV file to enable upload."
                : "Choose a file (PDF, CSV, or Excel) to enable upload — max 20 MB."}
            </p>
          ) : null}
          {error && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
              ✗ {error}
            </div>
          )}

          {/* Success result */}
          {result?.success && (
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 space-y-2">
              <p className="font-semibold text-emerald-300">
                ✓ Upload Complete — {result.institution || "Document"} processed
              </p>
              {result.date_range && (
                <p className="text-xs text-white/50">Period: {result.date_range}</p>
              )}
              <div className="grid grid-cols-3 gap-3 mt-3">
                {[
                  { label: "Extracted", value: result.extracted, color: "text-white" },
                  { label: "Imported", value: result.imported, color: "text-emerald-300" },
                  { label: "Duplicates Skipped", value: result.duplicates, color: "text-amber-300" },
                ].map((s) => (
                  <div key={s.label} className="rounded-xl border border-white/10 bg-white/[0.04] p-3 text-center">
                    <p className={`text-xl font-bold ${s.color}`}>{s.value ?? 0}</p>
                    <p className="text-[11px] text-white/50">{s.label}</p>
                  </div>
                ))}
              </div>
              {result.internal_transfers_skipped > 0 && (
                <p className="text-xs text-white/40">
                  {result.internal_transfers_skipped} internal transfer(s) excluded from import.
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── HISTORY PANEL ──────────────────────────────────────────────── */}
      {tab === "history" && (
        <div className="rounded-2xl border border-white/10 bg-[#111827] p-6">
          <h3 className="mb-4 text-lg font-bold text-white">Upload History</h3>
          {history.length === 0 ? (
            <p className="text-sm text-white/40">No uploads yet. Upload your first statement above.</p>
          ) : (
            <div className="space-y-3">
              {history.map((u) => (
                <div key={u.id} className="flex items-start justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-4">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-white">{u.file_name}</p>
                    <p className="mt-0.5 text-xs text-white/40">
                      {u.institution_name ?? "—"}
                      {u.source_type ? ` · ${u.source_type.replace("_", " ")}` : ""}
                      {u.file_size_kb ? ` · ${u.file_size_kb} KB` : ""}
                    </p>
                    <p className="mt-1 text-xs text-white/30">
                      {u.uploaded_at ? new Date(u.uploaded_at).toLocaleString("en-IN") : ""}
                    </p>
                  </div>
                  <div className="shrink-0 text-right space-y-1">
                    <Badge status={u.extraction_status} />
                    {u.extraction_status === "completed" && (
                      <p className="text-xs text-white/40">
                        {u.rows_imported}/{u.rows_extracted} rows
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── SOURCES PANEL ──────────────────────────────────────────────── */}
      {tab === "sources" && (
        <div className="rounded-2xl border border-white/10 bg-[#111827] p-6">
          <h3 className="mb-4 text-lg font-bold text-white">Connected Sources</h3>
          {sources.length === 0 ? (
            <p className="text-sm text-white/40">No sources connected yet. Upload a statement to add one.</p>
          ) : (
            <div className="space-y-3">
              {sources.map((s) => {
                const icon =
                  s.source_type === "credit_card" ? "💳"
                  : s.source_type === "bank" || s.source_type === "bank_statement_pdf" ? "🏦"
                  : s.source_type === "upi" ? "📱"
                  : "📄";
                return (
                  <div key={s.id} className="flex items-center gap-4 rounded-xl border border-white/10 bg-white/[0.03] p-4">
                    <span className="text-2xl">{icon}</span>
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-white truncate">{s.institution_name}</p>
                      <p className="text-xs text-white/40">
                        {String(s.source_type || "").replace(/_/g, " ")}
                        {s.account_number_masked ? ` · ••${s.account_number_masked}` : ""}
                        {s.is_primary ? " · Primary" : ""}
                      </p>
                    </div>
                    <div className="text-right shrink-0 space-y-0.5">
                      <p className="text-sm font-bold text-white">{s.transactions_count ?? 0}</p>
                      <p className="text-[11px] text-white/40">transactions</p>
                      {s.last_upload && (
                        <p className="text-[10px] text-white/30">
                          Last upload {new Date(s.last_upload).toLocaleDateString("en-IN")}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
