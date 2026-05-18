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
import React, { lazy, Suspense, useEffect, useMemo, useState } from "react";
import SourceSelection from "./pages/Onboarding/SourceSelection";
import Dashboard from "./components/Dashboard/Dashboard";
import { AuroraBackground } from "./components/intro/AuroraBackground";
import FestivalPredictor from "./components/Festival/FestivalPredictor";
import FraudShieldPage from "./components/FraudShield/FraudShieldPage";
import PurchasePlanner from "./components/Purchase/PurchasePlanner";
import DarkPatternDetector from "./components/DarkPatterns/DarkPatternDetector";
import EMITrapDetector from "./components/EMI/EMITrapDetector";
import Sidebar from "./components/Layout/Sidebar";
import TopBar from "./components/Layout/TopBar";
import SmartReminderEngine from "./pages/SmartReminderEngine";
import SubscriptionConnect from "./pages/SubscriptionConnect";
import SubscriptionHub from "./pages/SubscriptionHub";
import AIAnalysisEngine from "./pages/AIAnalysisEngine";
import { isSubscriptionFlowConnected } from "./utils/subscriptionFlowStorage";
import { resolveSubscriptionConnection } from "./utils/resolveSubscriptionConnection";
import IntroFlow, { resetToIntroAuth } from "./components/intro/IntroFlow";
import { ToastProvider } from "./components/common/Toast";
import { SkeletonCard } from "./components/common/SkeletonCard";
import { useAuth } from "./context/AuthContext";
import { AppDataProvider } from "./context/AppDataContext";
import { FinancialProvider } from "./context/FinancialContext";
import { SubscriptionIntelligenceProvider } from "./context/SubscriptionIntelligenceContext";

const TransactionsTab = lazy(() => import("./components/app-tabs/TransactionsTab"));
const InsightsTab = lazy(() => import("./components/app-tabs/InsightsTab"));
const TripPlannerPage = lazy(() => import("./pages/AIActions/TripPlannerPage"));
const CyberSafeConnectPage = lazy(() => import("./pages/RiskAwareness/CyberSafeConnectPage"));
const ChainVaultPage = lazy(() => import("./components/FraudShield/index"));
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
  /** Always the JWT user — never another workspace id (prevents cross-user data leaks). */
  const workspaceUserId = useMemo(() => Number(user?.id) || 0, [user?.id]);
  /** Logged-in user only — subscription intelligence + device-link must match JWT (no workspace fallback). */
  const subscriptionOwnerId = workspaceUserId;
  const [darkMode, setDarkMode] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState("dashboard");
  /**
   * Subscriptions tab (no React Router in CRA shell):
   * connect → first-time device link | hub → two engines | ai-analysis | reminders
   */
  const [subscriptionsSubView, setSubscriptionsSubView] = useState("connect");
  /** After sign-in, show cinematic intro once per tab session before OTP / bank onboarding. */
  const [preOnboardIntroDone, setPreOnboardIntroDone] = useState(false);

  /** When opening Subscriptions, land on connect vs hub (local + server device link). */
  useEffect(() => {
    if (activeTab !== "subscriptions") return;
    if (!subscriptionOwnerId) {
      setSubscriptionsSubView("connect");
      return;
    }
    if (isSubscriptionFlowConnected(subscriptionOwnerId)) {
      setSubscriptionsSubView("hub");
    }
    let cancelled = false;
    (async () => {
      const connected = await resolveSubscriptionConnection(subscriptionOwnerId);
      if (!cancelled) {
        setSubscriptionsSubView(connected ? "hub" : "connect");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeTab, subscriptionOwnerId]);

  useEffect(() => {
    const onFlowChanged = (ev) => {
      const uid = Number(ev?.detail?.userId) || subscriptionOwnerId;
      if (uid === subscriptionOwnerId && isSubscriptionFlowConnected(subscriptionOwnerId)) {
        setSubscriptionsSubView("hub");
      }
    };
    window.addEventListener("ss-subscription-flow-changed", onFlowChanged);
    return () => window.removeEventListener("ss-subscription-flow-changed", onFlowChanged);
  }, [subscriptionOwnerId]);

  /** Remove stale `fraudTab` from URL when leaving 12-phase FraudShield (AI Intelligence). */
  useEffect(() => {
    if (activeTab === "fraud") return;
    try {
      const url = new URL(window.location.href);
      if (!url.searchParams.has("fraudTab")) return;
      url.searchParams.delete("fraudTab");
      const q = url.searchParams.toString();
      window.history.replaceState({}, "", `${url.pathname}${q ? `?${q}` : ""}${url.hash}`);
    } catch {
      /* ignore */
    }
  }, [activeTab]);

  /** Trips & Events removed from UI — send stale tab id to dashboard. */
  useEffect(() => {
    if (activeTab === "family-events") setActiveTab("dashboard");
  }, [activeTab]);

  /** Deep-link from notification actions → Risk Awareness / CyberSafe Connect. */
  useEffect(() => {
    const handler = (e) => {
      const tab = e.detail?.tab;
      if (tab) setActiveTab(tab);
      if (tab === "subscriptions" && e.detail?.subView) {
        setSubscriptionsSubView(e.detail.subView);
      }
    };
    window.addEventListener("smartspend:navigate", handler);
    return () => window.removeEventListener("smartspend:navigate", handler);
  }, []);

  /** Legacy `?fraudTab=cybersafe` → Risk Awareness sidebar tab. */
  useEffect(() => {
    try {
      const url = new URL(window.location.href);
      if (url.searchParams.get("fraudTab") !== "cybersafe") return;
      url.searchParams.delete("fraudTab");
      window.history.replaceState({}, "", url.toString());
      setActiveTab("cybersafe-connect");
    } catch {
      /* ignore */
    }
  }, []);

  /**
   * Deep-link paths:
   *   /fraud-shield, /fraud → AI Intelligence · 12-phase FraudShield
   *   /chain-vault          → Risk Awareness · ChainVault (consumer mock)
   */
  useEffect(() => {
    try {
      const url = new URL(window.location.href);
      const path = url.pathname.replace(/\/+$/, "") || "/";
      if (path === "/chain-vault" || path.endsWith("/chain-vault")) {
        setActiveTab("fraud-shield");
      } else if (
        path === "/fraud-shield" ||
        path.endsWith("/fraud-shield") ||
        path === "/fraud" ||
        path.endsWith("/fraud")
      ) {
        setActiveTab("fraud");
      }
    } catch {
      /* ignore */
    }
  }, []);

  /** Keep pathname in sync with the active fraud surface. */
  useEffect(() => {
    try {
      const url = new URL(window.location.href);
      if (activeTab === "fraud") {
        if (!url.pathname.endsWith("/fraud-shield")) {
          url.pathname = "/fraud-shield";
          window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
        }
        return;
      }
      if (activeTab === "fraud-shield") {
        if (!url.pathname.endsWith("/chain-vault")) {
          url.pathname = "/chain-vault";
          window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
        }
        return;
      }
      if (url.pathname.endsWith("/fraud-shield") || url.pathname.endsWith("/chain-vault")) {
        url.pathname = "/";
        const q = url.searchParams.toString();
        window.history.replaceState({}, "", `${url.pathname}${q ? `?${q}` : ""}${url.hash}`);
      }
    } catch {
      /* ignore */
    }
  }, [activeTab]);

  /** Clear CyberSafe screen param when leaving Risk Awareness tab. */
  useEffect(() => {
    if (activeTab === "cybersafe-connect") return;
    try {
      const url = new URL(window.location.href);
      if (!url.searchParams.has("cybersafeScreen")) return;
      url.searchParams.delete("cybersafeScreen");
      const q = url.searchParams.toString();
      window.history.replaceState({}, "", `${url.pathname}${q ? `?${q}` : ""}${url.hash}`);
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

  const selectedUser = user;

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

  if (authLoading) {
    return (
      <ToastProvider>
        <div className="app-shell">
          <div style={{ marginTop: 24, padding: "0 16px" }}>
            <p className="text-sm text-gray-400" style={{ marginBottom: 12 }}>
              Connecting to your account…
            </p>
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
          onBack={async () => {
            try {
              if (user?.id) {
                window.sessionStorage.removeItem(`ss_pre_onboard_intro_done_${user.id}`);
              }
              window.sessionStorage.removeItem("ss_source_selection");
            } catch {
              /* ignore */
            }
            setPreOnboardIntroDone(false);
            setNeedsSourceSelection(false);
            resetToIntroAuth("signin");
            await logout();
          }}
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
      <AppDataProvider>
      <FinancialProvider>
        <SubscriptionIntelligenceProvider>
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
            userId={workspaceUserId}
            month={month}
            year={year}
            onMonthChange={setMonth}
            onYearChange={setYear}
            onTabChange={setActiveTab}
            onLogout={logout}
          />

          <div className="p-4 pb-28 pt-4 sm:p-5 md:pb-7 lg:p-7">
                <div key={activeTab} className="tab-panel-enter">
                {activeTab === "dashboard" && (
                  <Dashboard
                    key={workspaceUserId}
                    userId={workspaceUserId}
                    month={month}
                    year={year}
                    onMonthChange={setMonth}
                    onYearChange={setYear}
                    setActiveTab={setActiveTab}
                  />
                )}
                {activeTab === "transactions" && (
                  <Suspense fallback={<SkeletonCard lines={4} height={88} />}>
                    <TransactionsTab key={workspaceUserId} userId={workspaceUserId} month={month} year={year} />
                  </Suspense>
                )}
                {activeTab === "insights" && (
                  <Suspense fallback={<SkeletonCard lines={4} height={88} />}>
                    <InsightsTab
                      key={workspaceUserId}
                      userId={workspaceUserId}
                      month={month}
                      year={year}
                      setActiveTab={setActiveTab}
                    />
                  </Suspense>
                )}
                {activeTab === "simulator" && (
                  <Suspense fallback={<SkeletonCard lines={4} height={88} />}>
                    <SimulatorTab
                      key={workspaceUserId}
                      userId={workspaceUserId}
                      month={month}
                      year={year}
                      setActiveTab={setActiveTab}
                    />
                  </Suspense>
                )}
                {activeTab === "settings" && (
                  <Suspense fallback={<SkeletonCard lines={2} height={72} />}>
                    <SettingsTab
                      key={workspaceUserId}
                      onOpenAdmin={() => setActiveTab("admin")}
                      userId={workspaceUserId}
                      onLeave={() => setActiveTab("dashboard")}
                    />
                  </Suspense>
                )}
                {activeTab === "admin" && (
                  <Suspense fallback={<SkeletonCard lines={4} height={120} />}>
                    <AdminDiagnostics onExit={() => setActiveTab("settings")} />
                  </Suspense>
                )}
                {activeTab === "emi" && <EMITrapDetector key={workspaceUserId} userId={workspaceUserId} />}
                {activeTab === "subscriptions" && subscriptionOwnerId > 0 && subscriptionsSubView === "connect" && (
                  <SubscriptionConnect
                    key={subscriptionOwnerId}
                    ownerId={subscriptionOwnerId}
                    onComplete={() => setSubscriptionsSubView("hub")}
                  />
                )}
                {activeTab === "subscriptions" && subscriptionOwnerId > 0 && subscriptionsSubView === "hub" && (
                  <SubscriptionHub
                    key={subscriptionOwnerId}
                    ownerId={subscriptionOwnerId}
                    onOpenAI={() => setSubscriptionsSubView("ai-analysis")}
                    onOpenReminders={() => setSubscriptionsSubView("reminders")}
                    onDisconnected={() => setSubscriptionsSubView("connect")}
                  />
                )}
                {activeTab === "subscriptions" && subscriptionOwnerId > 0 && subscriptionsSubView === "ai-analysis" && (
                  <AIAnalysisEngine
                    key={subscriptionOwnerId}
                    onBack={() => setSubscriptionsSubView("hub")}
                    onOpenReminders={() => setSubscriptionsSubView("reminders")}
                  />
                )}
                {activeTab === "subscriptions" && subscriptionOwnerId > 0 && subscriptionsSubView === "reminders" && (
                  <SmartReminderEngine key={subscriptionOwnerId} onBack={() => setSubscriptionsSubView("hub")} />
                )}
                {activeTab === "subscriptions" && !subscriptionOwnerId ? (
                  <div className="mx-auto max-w-lg rounded-2xl border border-white/10 bg-white/[0.04] p-6 text-center text-sm text-white/75">
                    Your account id is not available yet. Refresh the page or sign in again to use Subscription
                    intelligence.
                  </div>
                ) : null}
                {activeTab === "dark-patterns" && <DarkPatternDetector key={workspaceUserId} userId={workspaceUserId} />}
                {activeTab === "fraud" && (
                  <FraudShieldPage key={workspaceUserId} userId={workspaceUserId} userName={selectedUser?.name} />
                )}
                {activeTab === "purchase" && <PurchasePlanner key={workspaceUserId} userId={workspaceUserId} />}
                {activeTab === "festival" && <FestivalPredictor key={workspaceUserId} userId={workspaceUserId} />}
                {activeTab === "trip-planner" && (
                  <Suspense fallback={<SkeletonCard lines={4} height={120} />}>
                    <TripPlannerPage />
                  </Suspense>
                )}
                {activeTab === "cybersafe-connect" && (
                  <Suspense fallback={<SkeletonCard lines={4} height={120} />}>
                    <CyberSafeConnectPage />
                  </Suspense>
                )}
                {activeTab === "fraud-shield" && (
                  <Suspense fallback={<SkeletonCard lines={4} height={120} />}>
                    <ChainVaultPage onNavigate={setActiveTab} />
                  </Suspense>
                )}

                </div>
          </div>
        </div>
      </div>
        </SubscriptionIntelligenceProvider>
      </FinancialProvider>
      </AppDataProvider>
    </ToastProvider>
  );
};

export default App;
