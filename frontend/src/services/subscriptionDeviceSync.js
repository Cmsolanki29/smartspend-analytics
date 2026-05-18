import {
  postSubscriptionDeviceLink,
  postSubscriptionIntelRemindersScheduleUpcoming,
  postSubscriptionSimulateNextDay,
} from "./api";
import { getSubscriptionFlowState } from "../utils/subscriptionFlowStorage";

/**
 * Persist linked apps from the connect / add-apps flow to the backend (seeds usage + subscriptions,
 * evaluates verdicts, schedules reminders). Requires a valid JWT for `userId`.
 */
export async function syncLinkedAppsToBackend(userId, appIdsOverride) {
  const uid = Number(userId);
  if (!uid || Number.isNaN(uid)) {
    return { ok: false, reason: "bad_user" };
  }

  const apps =
    Array.isArray(appIdsOverride) && appIdsOverride.length > 0
      ? appIdsOverride
      : getSubscriptionFlowState(uid).apps;
  if (!apps || apps.length === 0) {
    return { ok: false, reason: "no_apps" };
  }

  await postSubscriptionDeviceLink(uid, {
    device_type: "simulated",
    permissions: {
      usage_access: true,
      app_activity: true,
      billing_reminder_access: true,
      notifications: true,
    },
    apps_linked: apps,
  });

  try {
    await postSubscriptionIntelRemindersScheduleUpcoming(uid);
  } catch {
    /* non-fatal */
  }

  for (let i = 0; i < 6; i += 1) {
    try {
      await postSubscriptionSimulateNextDay(uid);
    } catch {
      break;
    }
  }

  try {
    window.dispatchEvent(new Event("ss-subscription-intel-refresh"));
  } catch {
    /* ignore */
  }

  return { ok: true };
}
