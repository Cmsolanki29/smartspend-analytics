/**
 * ════════════════════════════════════════════════════════════════════
 * DESIGN RULE — TEXT COLOR HIERARCHY  (enforced app-wide)
 * ════════════════════════════════════════════════════════════════════
 *
 * PURPLE IS AN ACCENT COLOR. PURPLE IS **NEVER** BODY TEXT.
 *
 * ❌ NEVER use text-purple-* / text-violet-* / text-exiqo-glow for:
 *    paragraphs · descriptions · labels · subtitles · placeholders ·
 *    captions · metadata · empty states · helper text · tooltips
 *
 * ✅ Use the gray hierarchy for ALL prose:
 *    text-white      — page titles, hero numbers, card headings
 *    text-gray-300   — body paragraphs, descriptions
 *    text-gray-400   — subtitles, secondary info
 *    text-gray-500   — labels (UPPERCASE), captions, timestamps
 *    text-gray-600   — placeholder text
 *    text-gray-700   — disabled text
 *
 * ✅ Purple is OK ONLY for:
 *    single-word badges · active tab indicator · accent word in white text ·
 *    hover:text-violet-* states · decorative gradient lines
 *
 * See src/lib/design-tokens.ts for the full token reference.
 * ════════════════════════════════════════════════════════════════════
 */
import React, { lazy, Suspense, useEffect, useLayoutEffect, useMemo, useState } from "react";
import SourceSelection from "./pages/Onboarding/SourceSelection";
import Dashboard from "./components/Dashboard/Dashboard";
import { AuroraBackground } from "./components/intro/AuroraBackground";
import FestivalPredictor from "./components/Festival/FestivalPredictor";
import FraudShieldPage from "./components/FraudShield/FraudShieldPage";
import PurchasePlanner from "./components/Purchase/PurchasePlanner";
import DarkPatternDetector from "./components/DarkPatterns/DarkPatternDetector";
import EMITrapDetector from "./components/EMI/EMITrapDetector";
import FamilyEventsPage from "./components/FamilyEvents/FamilyEventsPage";
import Sidebar from "./components/Layout/Sidebar";
import TopBar from "./components/Layout/TopBar";
import SmartReminderEngine from "./pages/SmartReminderEngine";
import SubscriptionConnect from "./pages/SubscriptionConnect";
import SubscriptionHub from "./pages/SubscriptionHub";
import AIAnalysisEngine from "./pages/AIAnalysisEngine";
import { isSubscriptionFlowConnected } from "./utils/subscriptionFlowStorage";
import IntroFlow from "./components/intro/IntroFlow";
import { ToastProvider } from "./components/common/Toast";
import { SkeletonCard } from "./components/common/SkeletonCard";
import { useAuth } from "./context/AuthContext";
import { getUsers } from "./services/api";

const TransactionsTab = lazy(() => import("./components/app-tabs/TransactionsTab"));
const InsightsTab = lazy(() => import("./components/app-tabs/InsightsTab"));
/** Legacy `activeTab === "simulator"` only (sidebar tab removed); renders Insights. */
const SimulatorTab = lazy(() => import("./components/app-tabs/SimulatorTab"));
const SettingsTab = lazy(() => import("./components/app-tabs/SettingsTab"));
const AdminDiagnostics = lazy(() => import("./pages/admin/AdminDiagnostics"));

const App = () => {
  const { user, loading: authLoading, logout, isAuthenticated, reloadUser } = useAuth();

  // Set by IntroAuth after a successful SIGNUP (never after sign-in).
  const [needsSourceSelection, setNeedsSourceSelection] = useState(false);

  // Read the sessionStorage flag once isAuthenticated flips true (signup sets it after auth resolves).
  useEffect(() => {
    if (!isAuthenticated) return;
    try {
      if (window.sessionStorage.getItem("ss_source_selection") === "1") {
        setNeedsSourceSelection(true);
      }
    } catch { /* ignore */ }
  }, [isAuthenticated]);
  const [users, setUsers] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState(1);
  /** Logged-in user only — subscription intelligence + device-link must match JWT (no workspace fallback). */
  const subscriptionOwnerId = useMemo(() => Number(user?.id) || 0, [user?.id]);
  const [darkMode, setDarkMode] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState("dashboard");
  /**
   * Subscriptions tab (no React Router in CRA shell):
   * connect → first-time device link | hub → two engines | ai-analysis | reminders
   */
  const [subscriptionsSubView, setSubscriptionsSubView] = useState("connect");
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [userError, setUserError] = useState("");
  /** After sign-in, show cinematic intro once per tab session before OTP / bank onboarding. */
  const [preOnboardIntroDone, setPreOnboardIntroDone] = useState(false);

  /** When opening Subscriptions, land on connect vs hub (local flow state is keyed by JWT user id). */
  useLayoutEffect(() => {
    if (activeTab !== "subscriptions") return;
    if (!subscriptionOwnerId) {
      setSubscriptionsSubView("connect");
      return;
    }
    setSubscriptionsSubView(isSubscriptionFlowConnected(subscriptionOwnerId) ? "hub" : "connect");
  }, [activeTab, subscriptionOwnerId]);

  /** Remove stale `fraudTab` from URL when viewing other tabs (avoids confusion + stale deep-links). */
  useEffect(() => {
    if (activeTab === "fraud") return;
    try {
      const url = new URL(window.location.href);
      if (!url.searchParams.has("fraudTab")) return;
      url.searchParams.delete("fraudTab");
      const q = url.searchParams.toString();
      const next = `${url.pathname}${q ? `?${q}` : ""}${url.hash}`;
      window.history.replaceState({}, "", next);
    } catch {
      /* ignore */
    }
  }, [activeTab]);

  /** Legacy sidebar tab ids → unified FraudShield hub + URL sub-tab. */
  useEffect(() => {
    const map = {
      "trust-center": "overview",
      "ai-performance": "overview",
      "alerts-center": "alerts",
      "behavior-profile": "behavior",
      "device-trust": "devices",
      investigations: "investigations",
      orchestrator: "overview",
      "dnn-shadow": "overview",
      "gnn-training": "overview",
    };
    const fraudTab = map[activeTab];
    if (!fraudTab) return;
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("fraudTab", fraudTab);
      window.history.replaceState({}, "", url.toString());
    } catch {
      /* ignore */
    }
    setActiveTab("fraud");
  }, [activeTab]);

  const today = useMemo(() => new Date(), []);
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [year, setYear] = useState(today.getFullYear());

  const selectedUser = useMemo(
    () => (users || []).find((u) => u.id === selectedUserId),
    [users, selectedUserId]
  );

  useEffect(() => {
    document.documentElement.classList.toggle("light", !darkMode);
    document.body.classList.toggle("light", !darkMode);
  }, [darkMode]);

  useEffect(() => {
    if (!user?.id || user.onboarding_completed === true) {
      setPreOnboardIntroDone(false);
      return;
    }
    try {
      setPreOnboardIntroDone(
        window.sessionStorage.getItem(`ss_pre_onboard_intro_done_${user.id}`) === "1"
      );
    } catch {
      setPreOnboardIntroDone(false);
    }
  }, [user?.id, user?.onboarding_completed]);

  useEffect(() => {
    if (!isAuthenticated || !user) {
      setUsers([]);
      setLoadingUsers(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoadingUsers(true);
      setUserError("");
      setSelectedUserId(user.id);
      try {
        const response = await getUsers();
        if (cancelled) return;
        setUsers(response || []);
        if (response?.length && !response.find((u) => u.id === user.id)) {
          setSelectedUserId(response[0].id);
        }
      } catch (error) {
        if (!cancelled) setUserError(error.message || "Unable to load users");
      } finally {
        if (!cancelled) setLoadingUsers(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, user]);

  if (authLoading) {
    return (
      <ToastProvider>
        <div className="app-shell">
          <div style={{ marginTop: 24 }}>
            <SkeletonCard lines={4} height={88} />
          </div>
        </div>
      </ToastProvider>
    );
  }

  if (!isAuthenticated) {
    // Cinematic intro flow: splash -> intro story -> get started -> auth -> dashboard.
    // Returning users (smartspend.seenIntro=true) skip straight to /auth/signin.
    return (
      <ToastProvider>
        <IntroFlow
          onComplete={() => {
            /* AuthContext flips isAuthenticated, which unmounts the flow. */
          }}
        />
      </ToastProvider>
    );
  }

  // Fresh signup: skip cinematic pre-onboard intro → go straight to source selection.
  const skipPreOnboardIntro =
    needsSourceSelection ||
    (() => {
      try {
        return window.sessionStorage.getItem("ss_source_selection") === "1";
      } catch {
        return false;
      }
    })();

  if (user && user.onboarding_completed !== true && !preOnboardIntroDone && !skipPreOnboardIntro) {
    return (
      <ToastProvider>
        <IntroFlow
          variant="preOnboarding"
          onComplete={() => {
            try {
              if (user?.id) {
                window.sessionStorage.setItem(`ss_pre_onboard_intro_done_${user.id}`, "1");
              }
            } catch {
              /* ignore */
            }
            setPreOnboardIntroDone(true);
          }}
        />
      </ToastProvider>
    );
  }

  // All incomplete onboarding → Source Selection (replaces old OTP/bank onboarding page).
  if (user && user.onboarding_completed !== true) {
    return (
      <ToastProvider>
        <SourceSelection
          userId={user.id}
          onComplete={async () => {
            await reloadUser();
            try {
              window.sessionStorage.removeItem("ss_source_selection");
            } catch {
              /* ignore */
            }
            setNeedsSourceSelection(false);
          }}
        />
      </ToastProvider>
    );
  }

  return (
    <ToastProvider>
      <div className="relative min-h-screen overflow-hidden bg-[#070418]">
        <AuroraBackground variant="app" />

        <Sidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed((v) => !v)}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          onLogout={logout}
        />

        <div
          style={{ marginLeft: sidebarCollapsed ? 80 : 256 }}
          className="relative z-10 min-h-screen transition-all duration-500 ease-brand max-md:!ml-0"
        >
          <TopBar
            userName={selectedUser?.name || user?.name || user?.email || "User"}
            userEmail={user?.email}
            userId={selectedUserId}
            month={month}
            year={year}
            onMonthChange={setMonth}
            onYearChange={setYear}
            onTabChange={setActiveTab}
            onLogout={logout}
          />

          <div className="p-4 pb-28 pt-4 sm:p-5 md:pb-7 lg:p-7">
            {loadingUsers ? (
              <div style={{ marginTop: 4 }}>
                <SkeletonCard lines={4} height={88} />
              </div>
            ) : userError ? (
              <div className="error-card glass-card" style={{ marginTop: 4 }}>
                <p>Could not load users: {userError}</p>
                <button type="button" onClick={() => window.location.reload()}>
                  Retry
                </button>
              </div>
            ) : (
              <>
                <div key={activeTab} className="tab-panel-enter">
                {activeTab === "dashboard" && (
                  <Dashboard
                    userId={selectedUserId}
                    month={month}
                    year={year}
                    onMonthChange={setMonth}
                    onYearChange={setYear}
                    setActiveTab={setActiveTab}
                  />
                )}
                {activeTab === "transactions" && (
                  <Suspense fallback={<SkeletonCard lines={4} height={88} />}>
                    <TransactionsTab userId={selectedUserId} month={month} year={year} />
                  </Suspense>
                )}
                {activeTab === "insights" && (
                  <Suspense fallback={<SkeletonCard lines={4} height={88} />}>
                    <InsightsTab
                      userId={selectedUserId}
                      month={month}
                      year={year}
                      setActiveTab={setActiveTab}
                    />
                  </Suspense>
                )}
                {activeTab === "simulator" && (
                  <Suspense fallback={<SkeletonCard lines={4} height={88} />}>
                    <SimulatorTab
                      userId={selectedUserId}
                      month={month}
                      year={year}
                      setActiveTab={setActiveTab}
                    />
                  </Suspense>
                )}
                {activeTab === "settings" && (
                  <Suspense fallback={<SkeletonCard lines={2} height={72} />}>
                    <SettingsTab
                      onOpenAdmin={() => setActiveTab("admin")}
                      userId={selectedUserId}
                      onLeave={() => setActiveTab("dashboard")}
                    />
                  </Suspense>
                )}
                {activeTab === "admin" && (
                  <Suspense fallback={<SkeletonCard lines={4} height={120} />}>
                    <AdminDiagnostics onExit={() => setActiveTab("settings")} />
                  </Suspense>
                )}
                {activeTab === "emi" && <EMITrapDetector userId={selectedUserId} />}
                {activeTab === "subscriptions" && subscriptionOwnerId > 0 && subscriptionsSubView === "connect" && (
                  <SubscriptionConnect
                    ownerId={subscriptionOwnerId}
                    onComplete={() => setSubscriptionsSubView("hub")}
                  />
                )}
                {activeTab === "subscriptions" && subscriptionOwnerId > 0 && subscriptionsSubView === "hub" && (
                  <SubscriptionHub
                    ownerId={subscriptionOwnerId}
                    onOpenAI={() => setSubscriptionsSubView("ai-analysis")}
                    onOpenReminders={() => setSubscriptionsSubView("reminders")}
                    onDisconnected={() => setSubscriptionsSubView("connect")}
                  />
                )}
                {activeTab === "subscriptions" && subscriptionOwnerId > 0 && subscriptionsSubView === "ai-analysis" && (
                  <AIAnalysisEngine
                    onBack={() => setSubscriptionsSubView("hub")}
                    onOpenReminders={() => setSubscriptionsSubView("reminders")}
                  />
                )}
                {activeTab === "subscriptions" && subscriptionOwnerId > 0 && subscriptionsSubView === "reminders" && (
                  <SmartReminderEngine onBack={() => setSubscriptionsSubView("hub")} />
                )}
                {activeTab === "subscriptions" && !subscriptionOwnerId ? (
                  <div className="mx-auto max-w-lg rounded-2xl border border-white/10 bg-white/[0.04] p-6 text-center text-sm text-white/75">
                    Your account id is not available yet. Refresh the page or sign in again to use Subscription
                    intelligence.
                  </div>
                ) : null}
                {activeTab === "dark-patterns" && <DarkPatternDetector userId={selectedUserId} />}
                {activeTab === "fraud" && (
                  <FraudShieldPage userId={selectedUserId} userName={selectedUser?.name} />
                )}
                {activeTab === "purchase" && <PurchasePlanner userId={selectedUserId} />}
                {activeTab === "festival" && <FestivalPredictor userId={selectedUserId} />}
                {activeTab === "family-events" && <FamilyEventsPage userId={selectedUserId} />}

                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </ToastProvider>
  );
};

export default App;
