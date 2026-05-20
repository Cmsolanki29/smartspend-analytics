import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AuroraBackground } from "./AuroraBackground";
import { GlassCard } from "./GlassCard";
import { GetStartedScreen } from "./GetStartedScreen";
import { GradientButton } from "./GradientButton";
import { IntroAuth, type AuthMode } from "./IntroAuth";
import { IntroStory } from "./IntroStory";
import { ShieldMark } from "./ShieldMark";
import { SplashScreen } from "./SplashScreen";

const BRAND_EASE = [0.22, 1, 0.36, 1] as const;

export const SEEN_INTRO_KEY = "smartspend.seenIntro";

/** Default unauthenticated flow (splash → … → auth). */
export const SESSION_STEP_KEY_DEFAULT = "smartspend.introStep";
/** Logged-in users who still need onboarding — separate storage so it does not collide with the sign-in flow. */
export const SESSION_STEP_KEY_PRE_ONBOARD = "smartspend.introStep.preOnboard";

/** After onboarding back: open sign-in / sign-up (IntroAuth), not splash or story. */
export function resetToIntroAuth(mode: AuthMode = "signin") {
  try {
    window.localStorage.setItem(SEEN_INTRO_KEY, "true");
    window.sessionStorage.removeItem(SESSION_STEP_KEY_PRE_ONBOARD);
    window.sessionStorage.setItem(SESSION_STEP_KEY_DEFAULT, "auth");
    window.location.hash = mode === "signup" ? "#signup" : "#signin";
  } catch {
    /* ignore */
  }
}

export type IntroStep = "splash" | "intro" | "get-started" | "auth" | "pre-onboard-cta";

export type IntroFlowProps = {
  onComplete: () => void;
  /**
   * signIn: full path including Get started + IntroAuth (default).
   * preOnboarding: splash → intro → one CTA → onComplete (user is already authenticated).
   */
  variant?: "signIn" | "preOnboarding";
};

const SHIELD_LAYOUT_ID = "ssShieldMark";

function readSessionStep(storageKey: string): IntroStep | null {
  try {
    const v = window.sessionStorage.getItem(storageKey);
    if (
      v === "splash" ||
      v === "intro" ||
      v === "get-started" ||
      v === "auth" ||
      v === "pre-onboard-cta"
    ) {
      return v as IntroStep;
    }
    return null;
  } catch {
    return null;
  }
}

function writeSessionStep(storageKey: string, step: IntroStep) {
  try {
    window.sessionStorage.setItem(storageKey, step);
  } catch {
    /* ignore */
  }
}

function safeWriteFlag() {
  try {
    window.localStorage.setItem(SEEN_INTRO_KEY, "true");
  } catch { /* ignore */ }
}

function hasSeenIntroBefore(): boolean {
  try {
    return window.localStorage.getItem(SEEN_INTRO_KEY) === "true";
  } catch {
    return false;
  }
}

/** Returning visitors skip splash/story and land on sign-in (App.jsx comment was not wired). */
function initialIntroStep(sessionKey: string, variant: IntroFlowProps["variant"]): IntroStep {
  const saved = readSessionStep(sessionKey);
  if (saved) {
    if (variant === "preOnboarding" && (saved === "get-started" || saved === "auth")) {
      return "splash";
    }
    return saved;
  }
  if (variant !== "preOnboarding" && hasSeenIntroBefore()) {
    return "auth";
  }
  return "splash";
}

/**
 * Top-level orchestrator for the intro flow.
 *
 * Behavior:
 *   - New tab / new window  → always starts from "splash" (sessionStorage empty)
 *   - Refresh on same tab   → resumes on same step (sessionStorage survives refresh)
 *   - After sign-in         → App.jsx isAuthenticated=true, IntroFlow unmounts
 */
export function IntroFlow({ onComplete, variant = "signIn" }: IntroFlowProps) {
  const sessionKey =
    variant === "preOnboarding" ? SESSION_STEP_KEY_PRE_ONBOARD : SESSION_STEP_KEY_DEFAULT;

  const [step, setStep] = useState<IntroStep>(() => initialIntroStep(sessionKey, variant));
  const [authMode, setAuthMode] = useState<AuthMode>("signin");
  /** Bumps when user replays splash from Get Started (forces fresh SplashScreen mount). */
  const [splashReplayKey, setSplashReplayKey] = useState(0);

  const markSeen = useCallback(() => {
    safeWriteFlag();
  }, []);

  const finishPreOnboarding = useCallback(() => {
    markSeen();
    onComplete();
  }, [markSeen, onComplete]);

  const fromSplash = useCallback(() => {
    writeSessionStep(sessionKey, "intro");
    setStep("intro");
  }, [sessionKey]);

  const fromIntro = useCallback(() => {
    if (variant === "preOnboarding") {
      writeSessionStep(sessionKey, "pre-onboard-cta");
      setStep("pre-onboard-cta");
      return;
    }
    writeSessionStep(sessionKey, "get-started");
    setStep("get-started");
  }, [sessionKey, variant]);

  const skipToAuth = useCallback(
    (mode: AuthMode = "signin") => {
      if (variant === "preOnboarding") {
        finishPreOnboarding();
        return;
      }
      markSeen();
      writeSessionStep(sessionKey, "auth");
      setAuthMode(mode);
      setStep("auth");
    },
    [finishPreOnboarding, markSeen, sessionKey, variant]
  );

  const fromGetStartedToCreate = useCallback(() => {
    markSeen();
    writeSessionStep(sessionKey, "auth");
    setAuthMode("signup");
    setStep("auth");
  }, [markSeen, sessionKey]);

  const fromGetStartedToSignin = useCallback(() => {
    markSeen();
    writeSessionStep(sessionKey, "auth");
    setAuthMode("signin");
    setStep("auth");
  }, [markSeen, sessionKey]);

  const onAuthBack = useCallback(() => {
    writeSessionStep(sessionKey, "get-started");
    setStep("get-started");
  }, [sessionKey]);

  const fromGetStartedToSplash = useCallback(() => {
    writeSessionStep(sessionKey, "splash");
    setSplashReplayKey((k) => k + 1);
    // Next frame: let Get Started unmount so layoutId does not fight splash replay.
    requestAnimationFrame(() => setStep("splash"));
  }, [sessionKey]);

  const onAuthenticated = useCallback(() => {
    markSeen();
    onComplete();
  }, [markSeen, onComplete]);

  // Write initial step to sessionStorage on first mount so refresh stays on same screen.
  useEffect(() => {
    writeSessionStep(sessionKey, step);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Defensive: if the URL hash includes #signup or #signin, deep-link.
  useEffect(() => {
    if (variant === "preOnboarding") return;
    const hash = (window.location.hash || "").toLowerCase();
    if (hash.includes("signup")) {
      setAuthMode("signup");
      setStep("auth");
    } else if (hash.includes("signin") || hash.includes("login")) {
      setAuthMode("signin");
      setStep("auth");
    }
  }, [variant]);

  // NOTE: We intentionally use the default ("sync") AnimatePresence mode here
  // — not "wait" — because the splash → intro shield morph relies on both
  // ShieldMark components (sharing layoutId="ssShieldMark") being present
  // simultaneously during the transition so Framer Motion can FLIP between them.
  return (
    <AnimatePresence>
      {step === "splash" ? (
        <motion.div
          key="splash"
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, transition: { duration: 0.4, ease: BRAND_EASE } }}
        >
          <SplashScreen
            key={`splash-run-${splashReplayKey}`}
            onComplete={fromSplash}
            onSkip={() => skipToAuth("signin")}
            shieldLayoutId={
              splashReplayKey === 0 ? SHIELD_LAYOUT_ID : undefined
            }
          />
        </motion.div>
      ) : null}

      {step === "intro" ? (
        <motion.div
          key="intro"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0, transition: { duration: 0.55, ease: BRAND_EASE } }}
          exit={{ opacity: 0, transition: { duration: 0.35, ease: BRAND_EASE } }}
        >
          <IntroStory
            onFinish={fromIntro}
            onSkip={() => skipToAuth("signin")}
            shieldLayoutId={SHIELD_LAYOUT_ID}
          />
        </motion.div>
      ) : null}

      {step === "get-started" ? (
        <motion.div
          key="get-started"
          initial={{ opacity: 0, scale: 0.985 }}
          animate={{
            opacity: 1,
            scale: 1,
            transition: { duration: 0.55, ease: BRAND_EASE },
          }}
          exit={{ opacity: 0, transition: { duration: 0.35, ease: BRAND_EASE } }}
        >
          <GetStartedScreen
            onCreate={fromGetStartedToCreate}
            onSignIn={fromGetStartedToSignin}
            onBackToSplash={fromGetStartedToSplash}
            shieldLayoutId={SHIELD_LAYOUT_ID}
          />
        </motion.div>
      ) : null}

      {step === "pre-onboard-cta" ? (
        <motion.div
          key="pre-onboard-cta"
          initial={{ opacity: 0, scale: 0.985 }}
          animate={{
            opacity: 1,
            scale: 1,
            transition: { duration: 0.55, ease: BRAND_EASE },
          }}
          exit={{ opacity: 0, transition: { duration: 0.35, ease: BRAND_EASE } }}
          className="relative flex min-h-[100dvh] w-full items-center justify-center overflow-hidden bg-[#070418] font-sans text-ss-ink"
        >
          <AuroraBackground starCount={56} tone="cool" />
          <header className="absolute inset-x-0 top-0 z-10 flex items-center justify-between px-5 pt-5 md:px-10 md:pt-7">
            <div className="flex items-center gap-2.5">
              <ShieldMark layoutId={SHIELD_LAYOUT_ID} stage="complete" size={36} />
              <span className="font-heading text-base font-semibold tracking-tight text-white">
                SmartSpend
              </span>
            </div>
          </header>
          <motion.div
            className="relative z-10 w-full max-w-md px-5 md:max-w-lg"
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.65, ease: BRAND_EASE }}
          >
            <GlassCard padding="lg" elevation="raised" className="text-center">
              <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center">
                <ShieldMark stage="complete" size={64} />
              </div>
              <h1 className="font-heading text-[clamp(1.5rem,4vw,2.1rem)] font-semibold leading-tight tracking-tight text-white">
                Next: verify and link
              </h1>
              <p className="mx-auto mt-4 max-w-sm text-[15px] leading-relaxed text-ss-mute">
                Confirm your mobile with OTP, then link your bank securely. You can resume anytime.
              </p>
              <div className="mt-8">
                <GradientButton full onClick={finishPreOnboarding} trailingIcon={<ArrowRight size={18} />}>
                  Continue to verification
                </GradientButton>
              </div>
            </GlassCard>
          </motion.div>
        </motion.div>
      ) : null}

      {step === "auth" ? (
        <motion.div
          key="auth"
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0, transition: { duration: 0.55, ease: BRAND_EASE } }}
          exit={{ opacity: 0, transition: { duration: 0.35, ease: BRAND_EASE } }}
        >
          <IntroAuth
            initialMode={authMode}
            onAuthenticated={onAuthenticated}
            onBack={onAuthBack}
            shieldLayoutId={SHIELD_LAYOUT_ID}
          />
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

export default IntroFlow;
