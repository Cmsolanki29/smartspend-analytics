/**
 * Broadcast financial mutations so Dashboard + AI Insights refetch health score.
 */
import { refreshHealthScore } from "../services/api";

export function notifyFinancialMutation(userId, detail = {}) {
  if (userId == null) return;
  const payload = { userId, ...detail };
  try {
    window.dispatchEvent(new CustomEvent("smartspend:health-score-changed", { detail: payload }));
    window.dispatchEvent(new CustomEvent("smartspend:purchase-goals-changed", { detail: payload }));
    window.dispatchEvent(new CustomEvent("smartspend-financial-sync", { detail: payload }));
  } catch {
    /* ignore */
  }
}

/**
 * Persist health on server, then notify all listeners (real-time score update).
 */
export async function syncHealthScoreAfterMutation(
  userId,
  { month, year, scope } = {}
) {
  let health = null;
  try {
    health = await refreshHealthScore(userId, month, year, scope);
  } catch {
    /* listeners will still refetch via GET */
  }
  notifyFinancialMutation(userId, {
    month,
    year,
    scope,
    score: health?.score ?? null,
    grade: health?.grade ?? null,
    trend: health?.trend ?? null,
    health_band: health?.health_band ?? null,
    health_label: health?.health_label ?? null,
  });
  return health;
}
