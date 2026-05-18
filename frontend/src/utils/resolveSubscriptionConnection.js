import { getSubscriptionIntelligenceHub } from "../services/api";
import {
  getSubscriptionFlowState,
  isSubscriptionFlowConnected,
  setSubscriptionFlowConnected,
} from "./subscriptionFlowStorage";

/** Android package → frontend app id (when backend stored packages). */
const PACKAGE_TO_APP_ID = {
  "com.netflix.mediaclient": "netflix",
  "com.spotify.music": "spotify",
  "com.google.android.youtube": "youtube",
  "in.startv.hotstar": "hotstar",
  "in.amazon.mShop.android.shopping": "amazon_prime",
  "com.openai.chatgpt": "chatgpt",
  "com.notion.android": "notion",
  "com.canva.editor": "canva",
  "com.linkedin.android": "linkedin",
  "com.adobe.reader": "adobe",
};

function normalizeAppIds(raw) {
  const out = [];
  for (const item of raw || []) {
    const s = String(item || "").trim();
    if (!s) continue;
    out.push(PACKAGE_TO_APP_ID[s] || s);
  }
  return [...new Set(out)];
}

function appIdsFromHub(hub) {
  const fromDevice = normalizeAppIds(hub?.device?.apps_linked);
  if (fromDevice.length > 0) return fromDevice;
  const fromConnected = normalizeAppIds(
    (hub?.connected_apps || []).map((row) => row?.app_package || row?.id)
  );
  return fromConnected;
}

/**
 * True when this user has completed device link (localStorage and/or Postgres).
 * Hydrates localStorage from the hub when the server already has a link.
 */
export async function resolveSubscriptionConnection(userId) {
  const uid = Number(userId);
  if (!uid || Number.isNaN(uid)) return false;

  if (isSubscriptionFlowConnected(uid)) {
    return true;
  }

  try {
    const hub = await getSubscriptionIntelligenceHub(uid);
    const linked = Boolean(hub?.device_linked);
    const apps = appIdsFromHub(hub);
    if (linked && apps.length > 0) {
      setSubscriptionFlowConnected(uid, apps);
      return true;
    }
    if (linked) {
      const cur = getSubscriptionFlowState(uid);
      if (cur.apps?.length > 0) {
        setSubscriptionFlowConnected(uid, cur.apps);
        return true;
      }
    }
  } catch {
    /* offline / API warming — fall back to local only */
  }

  return isSubscriptionFlowConnected(uid);
}
