/**
 * Shared document upload — used by signup (SourceSelection) and Settings (UploadStatement).
 * Both paths call POST /api/documents/upload → monster extraction pipeline.
 */
import { dispatchDataUpdated } from "../utils/refetchAll";
import { getAccessToken } from "./api";
import { getApiBaseUrl } from "./apiBaseUrl";

export const UPLOAD_ACCEPT =
  ".pdf,.csv,.xlsx,.xls,.txt,.jpg,.jpeg,.png,.tiff,.bmp,.webp";

export const UPLOAD_HINT = "Supports PDF, CSV, Excel, Images — max 20 MB";

export function buildUploadFormData({
  file,
  userId,
  sourceType,
  institutionName,
  accountNumberMasked,
}) {
  const form = new FormData();
  form.append("file", file);
  form.append("user_id", String(userId));
  form.append("source_type", sourceType);
  form.append("institution_name", institutionName.trim());
  if (accountNumberMasked?.trim()) {
    form.append("account_number_masked", accountNumberMasked.trim());
  }
  return form;
}

export function extractUploadError(data) {
  if (!data) return "Upload failed";
  const d = data.detail ?? data.error ?? data.message;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => e?.msg || JSON.stringify(e)).join("; ");
  if (d && typeof d === "object") return JSON.stringify(d);
  return "Upload failed";
}

/**
 * @param {object} opts
 * @param {File} opts.file
 * @param {number|string} opts.userId
 * @param {string} opts.sourceType
 * @param {string} opts.institutionName
 * @param {string} [opts.accountNumberMasked]
 * @param {string} [opts.addedVia] - 'onboarding_upload' | 'settings_upload'
 * @param {string} [opts.apiBase] - override API base (signup uses /api proxy)
 */
export async function uploadFinancialDocument({
  file,
  userId,
  sourceType,
  institutionName,
  accountNumberMasked,
  addedVia,
  apiBase,
}) {
  const token = getAccessToken();
  const base = apiBase ?? getApiBaseUrl();
  const form = buildUploadFormData({
    file,
    userId,
    sourceType,
    institutionName,
    accountNumberMasked,
  });
  if (addedVia) form.append("added_via", addedVia);

  const res = await fetch(`${base}/documents/upload`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });

  let data;
  try {
    data = await res.json();
  } catch {
    throw new Error("Server returned a non-JSON response. Is the API running?");
  }

  if (!res.ok || data.success === false) {
    throw new Error(extractUploadError(data));
  }
  if (typeof window !== "undefined") {
    const imported = Number(data?.imported ?? 0);
    if (imported > 0 || data?.data_updated) {
      dispatchDataUpdated({
        userId,
        sourceName: data?.source_name || data?.institution || institutionName,
      });
    }
    const sy = Number(data?.statement_year);
    const sm = Number(data?.statement_month);
    if (imported > 0 && sy > 0 && sm >= 1 && sm <= 12) {
      window.dispatchEvent(
        new CustomEvent("smartspend:set-view-month", {
          detail: { year: sy, month: sm, user_id: Number(userId) },
        })
      );
    }
  }
  return data;
}
