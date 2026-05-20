import { syncHealthScoreAfterMutation } from "./financialSync";

/**
 * Phase 1 global refresh — upload pipeline signals clients via this event.
 * Phase 3 will also listen on Socket.IO `data_updated`.
 */
export function dispatchDataUpdated({ userId, sourceName, month, year, scope } = {}) {
  try {
    window.dispatchEvent(
      new CustomEvent("smartspend:data-updated", {
        detail: {
          user_id: userId != null ? Number(userId) : undefined,
          source_name: sourceName || "Statement",
        },
      })
    );
    window.dispatchEvent(new Event("smartspend-financial-sync"));
    window.dispatchEvent(new Event("dashboardModeChanged"));
    if (userId != null) {
      syncHealthScoreAfterMutation(userId, { month, year, scope }).catch(() => {});
    }
  } catch {
    /* ignore */
  }
}

export function refetchAll(detail) {
  dispatchDataUpdated(detail);
}
