import React, { lazy, Suspense, useEffect, useMemo, useState } from "react";
import OnboardingPage from "./app/onboarding/page";
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
import SubscriptionGraveyard from "./components/Subscriptions/SubscriptionGraveyard";
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

const App = () => {
  const { user, loading: authLoading, logout, isAuthenticated } = useAuth();
  const [users, setUsers] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState(1);
  const [darkMode, setDarkMode] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [userError, setUserError] = useState("");
  /** After sign-in, show cinematic intro once per tab session before OTP / bank onboarding. */
  const [preOnboardIntroDone, setPreOnboardIntroDone] = useState(false);

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

  if (user && user.onboarding_completed !== true && !preOnboardIntroDone) {
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

  if (user && user.onboarding_completed !== true) {
    return (
      <ToastProvider>
        <OnboardingPage />
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
            userId={selectedUserId}
            month={month}
            year={year}
            onMonthChange={setMonth}
            onYearChange={setYear}
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
                    userName={selectedUser?.name}
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
                    <InsightsTab userId={selectedUserId} month={month} year={year} />
                  </Suspense>
                )}
                {activeTab === "simulator" && (
                  <Suspense fallback={<SkeletonCard lines={4} height={88} />}>
                    <SimulatorTab userId={selectedUserId} month={month} year={year} />
                  </Suspense>
                )}
                {activeTab === "settings" && (
                  <Suspense fallback={<SkeletonCard lines={2} height={72} />}>
                    <SettingsTab />
                  </Suspense>
                )}
                {activeTab === "emi" && <EMITrapDetector userId={selectedUserId} />}
                {activeTab === "subscriptions" && <SubscriptionGraveyard userId={selectedUserId} />}
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
