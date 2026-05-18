const key = (userId) => `ss_subscription_flow_${Number(userId) || 0}`;

/**
 * @returns {{ connected: boolean, apps: string[], grantedAt: string | null }}
 */
export function getSubscriptionFlowState(userId) {
  try {
    const raw = window.localStorage.getItem(key(userId));
    if (!raw) return { connected: false, apps: [], grantedAt: null };
    const data = JSON.parse(raw);
    return {
      connected: Boolean(data.connected),
      apps: Array.isArray(data.apps) ? data.apps : [],
      grantedAt: data.grantedAt || null,
    };
  } catch {
    return { connected: false, apps: [], grantedAt: null };
  }
}

export function isSubscriptionFlowConnected(userId) {
  const s = getSubscriptionFlowState(userId);
  return s.connected && Array.isArray(s.apps) && s.apps.length > 0;
}

export function setSubscriptionFlowConnected(userId, appIds) {
  const uniq = [...new Set((appIds || []).filter(Boolean))];
  window.localStorage.setItem(
    key(userId),
    JSON.stringify({
      connected: uniq.length > 0,
      apps: uniq,
      grantedAt: new Date().toISOString(),
    })
  );
  try {
    window.dispatchEvent(
      new CustomEvent("ss-subscription-flow-changed", { detail: { userId: Number(userId) || 0 } })
    );
  } catch {
    /* ignore */
  }
}

export function mergeSubscriptionApps(userId, newIds) {
  const cur = getSubscriptionFlowState(userId);
  const merged = [...new Set([...(cur.apps || []), ...(newIds || [])])];
  setSubscriptionFlowConnected(userId, merged);
}

export function clearSubscriptionFlow(userId) {
  try {
    window.localStorage.removeItem(key(userId));
  } catch {
    /* ignore */
  }
}
