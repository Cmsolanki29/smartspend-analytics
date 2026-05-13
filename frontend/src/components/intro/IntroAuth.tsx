import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  Apple,
  ArrowLeft,
  ArrowRight,
  Check,
  Eye,
  EyeOff,
  Github,
  ShieldCheck,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import {
  ChangeEvent,
  FormEvent,
  type HTMLAttributes,
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useAuth } from "../../context/AuthContext";
import { AuroraBackground } from "./AuroraBackground";
import { GlassCard } from "./GlassCard";
import { GradientButton } from "./GradientButton";
import { ShieldMark } from "./ShieldMark";

const BRAND_EASE = [0.22, 1, 0.36, 1] as const;

export type AuthMode = "signin" | "signup";

export type IntroAuthProps = {
  /** Initial active tab. */
  initialMode?: AuthMode;
  /** Called after successful auth. The orchestrator should clear the flow / route to dashboard. */
  onAuthenticated: () => void;
  /** Back to the get-started screen. */
  onBack: () => void;
  /** Layout id for the navbar shield morph. */
  shieldLayoutId?: string;
};

/* ============================ Floating-label input ============================ */

type FloatingInputProps = {
  id: string;
  label: string;
  type?: string;
  /** Use with `type="text"` so `.local` demo addresses are not blocked by the browser. */
  inputMode?: HTMLAttributes<HTMLInputElement>["inputMode"];
  value: string;
  onChange: (e: ChangeEvent<HTMLInputElement>) => void;
  autoComplete?: string;
  required?: boolean;
  trailing?: ReactNode;
};

function FloatingInput({
  id,
  label,
  type = "text",
  inputMode,
  value,
  onChange,
  autoComplete,
  required,
  trailing,
}: FloatingInputProps) {
  // Single-surface field: ONE border on the outer wrapper, transparent input inside.
  // Focus state collapses the border into a soft violet ring (no doubled outline).
  return (
    <div className="relative w-full rounded-2xl border border-white/10 bg-white/[0.04] transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-white/20 focus-within:border-transparent focus-within:bg-white/[0.06] focus-within:ring-2 focus-within:ring-violet-400/40">
      <input
        id={id}
        type={type}
        inputMode={inputMode}
        value={value}
        onChange={onChange}
        autoComplete={autoComplete}
        required={required}
        placeholder=" "
        className={`peer h-14 w-full border-0 bg-transparent text-[15px] text-white placeholder-transparent outline-none ring-0 focus:border-0 focus:outline-none focus:ring-0 ${
          trailing ? "pl-4 pr-12" : "px-4"
        } pb-1 pt-5`}
      />
      <label
        htmlFor={id}
        className="pointer-events-none absolute left-4 top-4 select-none text-[15px] text-white/50 transition-all duration-200 peer-focus:top-1.5 peer-focus:text-[11px] peer-focus:tracking-wide peer-focus:text-white/70 peer-[:not(:placeholder-shown)]:top-1.5 peer-[:not(:placeholder-shown)]:text-[11px] peer-[:not(:placeholder-shown)]:tracking-wide peer-[:not(:placeholder-shown)]:text-white/70"
      >
        {label}
      </label>
      {trailing ? (
        <div className="absolute right-3 top-1/2 -translate-y-1/2">
          {trailing}
        </div>
      ) : null}
    </div>
  );
}

/* ============================ Password strength meter ============================ */

function passwordStrength(p: string): 0 | 1 | 2 | 3 | 4 {
  if (!p) return 0;
  let score = 0;
  if (p.length >= 8) score++;
  if (/[A-Z]/.test(p) && /[a-z]/.test(p)) score++;
  if (/\d/.test(p)) score++;
  if (/[^A-Za-z0-9]/.test(p)) score++;
  // Bonus for very long passphrases
  if (p.length >= 14 && score < 4) score++;
  return Math.min(4, score) as 0 | 1 | 2 | 3 | 4;
}

const STRENGTH_LABELS = ["Too short", "Weak", "Fair", "Strong", "Excellent"] as const;
const STRENGTH_COLORS = ["#374151", "#EF4444", "#F97316", "#22D3EE", "#10B981"];

function StrengthMeter({ password }: { password: string }) {
  const score = passwordStrength(password);
  return (
    <div className="mt-2.5">
      <div className="flex gap-1.5">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-[5px] flex-1 overflow-hidden rounded-full bg-white/[0.06]"
          >
            <motion.div
              className="h-full rounded-full"
              initial={false}
              animate={{
                width: i < score ? "100%" : "0%",
                backgroundColor: STRENGTH_COLORS[Math.min(score, 4)],
              }}
              transition={{ duration: 0.45, ease: BRAND_EASE }}
            />
          </div>
        ))}
      </div>
      <p className="mt-1.5 text-[10.5px] font-semibold uppercase tracking-[0.16em] text-white/55">
        {password ? STRENGTH_LABELS[score] : "8+ characters with a number & symbol"}
      </p>
    </div>
  );
}

/* ============================ Social buttons ============================ */

function SocialBtn({
  icon,
  label,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  onClick?: () => void;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.button
      type="button"
      onClick={onClick}
      whileHover={reduce ? undefined : { y: -2 }}
      whileTap={reduce ? undefined : { scale: 0.95 }}
      transition={{ type: "spring", stiffness: 380, damping: 22 }}
      aria-label={label}
      className="flex h-12 w-12 items-center justify-center rounded-full border border-white/10 bg-white/[0.05] text-white/85 backdrop-blur-md transition-all duration-300 ease-brand hover:border-white/25 hover:bg-white/[0.1] hover:text-white hover:shadow-[0_0_24px_rgba(124,58,237,0.32)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
    >
      {icon}
    </motion.button>
  );
}

/* ============================ Showcase column ============================ */

function ShowcasePanel({ mode }: { mode: AuthMode }) {
  const reduce = useReducedMotion();

  return (
    <div className="relative h-full w-full overflow-hidden">
      {/* Animated mesh-gradient panel */}
      <div
        className={`absolute inset-0 ${reduce ? "" : "animate-ss-mesh"} bg-[length:300%_300%]`}
        style={{
          backgroundImage:
            "radial-gradient(at 18% 22%, rgba(124,58,237,0.55) 0px, transparent 55%), radial-gradient(at 80% 18%, rgba(236,72,153,0.45) 0px, transparent 55%), radial-gradient(at 65% 78%, rgba(34,211,238,0.4) 0px, transparent 55%), radial-gradient(at 22% 82%, rgba(168,85,247,0.45) 0px, transparent 55%), linear-gradient(135deg, #0F0A2E 0%, #070418 100%)",
        }}
      />
      {/* Grain veil */}
      <div
        className="absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
        aria-hidden
      />
      {/* Vignette */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_55%,rgba(7,4,24,0.55)_100%)]" />

      {/* Floating tilted dashboard preview */}
      <motion.div
        className="absolute left-1/2 top-1/2 hidden h-[460px] w-[520px] -translate-x-1/2 -translate-y-1/2 lg:block"
        style={{ perspective: 1200 }}
        initial={{ opacity: 0, y: 32 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: BRAND_EASE, delay: 0.1 }}
      >
        <motion.div
          className="relative h-full w-full"
          style={{ transformStyle: "preserve-3d" }}
          animate={
            reduce
              ? undefined
              : { rotateY: [-12, -8, -12], rotateX: [6, 4, 6], y: [0, -12, 0] }
          }
          transition={{ duration: 9, repeat: Infinity, ease: "easeInOut" }}
        >
          <DashboardPreview />
        </motion.div>

        {/* Orbiting chips */}
        <OrbitingChip
          label="+₹12,400 saved"
          color="cyan"
          orbit={{ x: -240, y: -120, delay: 0 }}
        />
        <OrbitingChip
          label="Fraud blocked"
          color="magenta"
          orbit={{ x: 230, y: -80, delay: 1.4 }}
        />
        <OrbitingChip
          label="Goal · 78%"
          color="violet"
          orbit={{ x: 200, y: 160, delay: 2.6 }}
        />
      </motion.div>

      {/* Mobile: ONE chip + condensed hero */}
      <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 lg:hidden">
        <div className="mx-auto flex max-w-md flex-col items-center px-6 text-center">
          <ShieldMark stage="complete" size={92} />
          <p className="mt-4 font-heading text-[clamp(1.4rem,5.5vw,2rem)] font-semibold leading-tight text-white">
            {mode === "signup" ? "Start your shield." : "Welcome back."}
          </p>
          <span className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-cyan-400/40 bg-cyan-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-cyan-100 shadow-[0_0_24px_rgba(34,211,238,0.28)]">
            <TrendingUp size={12} />
            +₹12,400 saved this month
          </span>
        </div>
      </div>

      {/* Bottom-left testimonial (desktop only) */}
      <motion.div
        className="absolute bottom-6 left-6 hidden max-w-[280px] lg:block"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: BRAND_EASE, delay: 0.5 }}
      >
        <GlassCard padding="sm">
          <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-cyan-300">
            <Sparkles size={11} />
            User story
          </div>
          <p className="mt-2 text-[13px] leading-relaxed text-white/85">
            “SmartSpend blocked a ₹52,000 hidden charge in seconds. It feels like a real
            guardian.”
          </p>
          <p className="mt-2 text-[11px] font-medium text-white/55">
            — Priya · early access
          </p>
        </GlassCard>
      </motion.div>
    </div>
  );
}

function DashboardPreview() {
  return (
    <div className="relative h-full w-full rounded-[28px] border border-white/15 bg-[#0E0826]/85 p-5 shadow-[0_30px_120px_rgba(0,0,0,0.6),0_0_0_1px_rgba(168,85,247,0.18)] backdrop-blur-2xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldMark stage="complete" size={22} />
          <span className="font-heading text-[13px] font-semibold text-white">SmartSpend</span>
        </div>
        <div className="flex gap-1.5">
          <span className="h-2 w-2 rounded-full bg-white/20" />
          <span className="h-2 w-2 rounded-full bg-white/20" />
          <span className="h-2 w-2 rounded-full bg-white/20" />
        </div>
      </div>

      {/* Hero number */}
      <div className="mt-5">
        <p className="text-[10.5px] font-semibold uppercase tracking-[0.18em] text-white/50">
          Available balance
        </p>
        <p className="mt-1 font-heading text-[34px] font-semibold leading-none text-white">
          ₹2,84,612
        </p>
        <p className="mt-1 text-[12px] text-emerald-300">+₹12,400 this month</p>
      </div>

      {/* Mini chart */}
      <svg viewBox="0 0 320 110" className="mt-4 h-24 w-full">
        <defs>
          <linearGradient id="dpGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#22D3EE" />
            <stop offset="100%" stopColor="#EC4899" />
          </linearGradient>
          <linearGradient id="dpFill" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="rgba(168,85,247,0.4)" />
            <stop offset="100%" stopColor="rgba(168,85,247,0)" />
          </linearGradient>
        </defs>
        <path
          d="M 0 82 C 30 70, 50 86, 80 64 S 130 30, 170 38 S 230 18, 320 10 L 320 110 L 0 110 Z"
          fill="url(#dpFill)"
        />
        <path
          d="M 0 82 C 30 70, 50 86, 80 64 S 130 30, 170 38 S 230 18, 320 10"
          stroke="url(#dpGrad)"
          strokeWidth="2.5"
          fill="none"
          strokeLinecap="round"
        />
      </svg>

      {/* Two mini cards */}
      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white/55">
            Fraud blocked
          </p>
          <p className="mt-0.5 font-heading text-[18px] font-semibold text-white">7</p>
          <p className="text-[10px] text-white/55">this month</p>
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white/55">
            Savings goal
          </p>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-white/[0.08]">
            <div className="h-full w-[78%] rounded-full bg-ss-brand" />
          </div>
          <p className="mt-1 text-[10px] text-white/55">78% to ₹50,000</p>
        </div>
      </div>
    </div>
  );
}

function OrbitingChip({
  label,
  color,
  orbit,
}: {
  label: string;
  color: "cyan" | "magenta" | "violet";
  orbit: { x: number; y: number; delay: number };
}) {
  const reduce = useReducedMotion();

  const tone =
    color === "cyan"
      ? { ring: "border-cyan-300/45", bg: "bg-cyan-400/15", text: "text-cyan-100", glow: "0 0 28px rgba(34,211,238,0.45)" }
      : color === "magenta"
      ? { ring: "border-pink-300/45", bg: "bg-pink-500/15", text: "text-pink-100", glow: "0 0 28px rgba(236,72,153,0.45)" }
      : { ring: "border-violet-300/45", bg: "bg-violet-500/15", text: "text-violet-100", glow: "0 0 28px rgba(124,58,237,0.45)" };

  return (
    <motion.span
      className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border px-3.5 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] backdrop-blur-md ${tone.ring} ${tone.bg} ${tone.text}`}
      style={{ boxShadow: tone.glow }}
      initial={{ opacity: 0, x: orbit.x, y: orbit.y, scale: 0.9 }}
      animate={
        reduce
          ? { opacity: 1, x: orbit.x, y: orbit.y, scale: 1 }
          : {
              opacity: 1,
              x: [orbit.x, orbit.x + 14, orbit.x - 8, orbit.x],
              y: [orbit.y, orbit.y - 12, orbit.y + 10, orbit.y],
              scale: [0.9, 1, 1, 1],
            }
      }
      transition={{
        duration: 7,
        repeat: reduce ? 0 : Infinity,
        ease: "easeInOut",
        delay: orbit.delay,
      }}
    >
      {label}
    </motion.span>
  );
}

/* ============================ Main IntroAuth ============================ */

export function IntroAuth({
  initialMode = "signup",
  onAuthenticated,
  onBack,
  shieldLayoutId = "ssShieldMark",
}: IntroAuthProps) {
  const reduce = useReducedMotion();
  const { signin, signup } = useAuth();

  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);

  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");
  const successTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (successTimerRef.current != null) {
        window.clearTimeout(successTimerRef.current);
        successTimerRef.current = null;
      }
    };
  }, []);

  // Reset transient state when switching tabs
  useEffect(() => {
    setError("");
    setSuccess(false);
  }, [mode]);

  const submit = useCallback(
    async (e: FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (busy) return;
      setBusy(true);
      setError("");
      try {
        if (mode === "signin") {
          await signin(email.trim(), password);
        } else {
          await signup({ name: name.trim(), email: email.trim(), password });
        }
        setBusy(false);
        setSuccess(true);
        if (successTimerRef.current != null) {
          window.clearTimeout(successTimerRef.current);
        }
        const delayMs = reduce ? 220 : 720;
        successTimerRef.current = window.setTimeout(() => {
          successTimerRef.current = null;
          onAuthenticated();
        }, delayMs);
      } catch (err: unknown) {
        setBusy(false);
        setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
      }
    },
    [busy, mode, email, password, name, signin, signup, onAuthenticated, reduce]
  );

  const submitLabel = mode === "signin" ? "Sign in" : "Create account";

  return (
    <div className="relative min-h-[100dvh] w-full overflow-hidden bg-[#070418] font-sans text-ss-ink">
      {/* Mobile background */}
      <div className="lg:hidden">
        <AuroraBackground starCount={36} />
      </div>

      {/* Back button — kept absolute, unchanged position/style. The SmartSpend
          brand mark has moved to the right panel's header row to prevent it
          ever overlapping the Sign In | Sign Up tab pill. */}
      <header className="absolute inset-x-0 top-0 z-30 flex items-center px-5 pt-5 lg:px-10 lg:pt-7">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.05] px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-white/75 backdrop-blur-md transition hover:border-white/25 hover:bg-white/[0.08] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
        >
          <ArrowLeft size={13} />
          Back
        </button>
      </header>

      {/* Two-column layout */}
      <div className="relative flex min-h-[100dvh] flex-col lg:flex-row">
        {/* LEFT — showcase (55% on lg, 35vh hero on mobile) */}
        <aside
          className="relative h-[35vh] min-h-[260px] w-full overflow-hidden lg:h-auto lg:min-h-[100dvh] lg:w-[55%]"
          aria-hidden
        >
          <ShowcasePanel mode={mode} />
        </aside>

        {/* RIGHT — form panel */}
        <main className="relative flex w-full flex-1 flex-col bg-[#070418] pb-32 lg:w-[45%] lg:pb-12">
          {/* Subtle radial wash */}
          <div
            className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_85%_50%_at_50%_15%,rgba(124,58,237,0.10),transparent_60%)]"
            aria-hidden
          />

          {/* Header row: tabs LEFT, SmartSpend brand RIGHT — never overlap. */}
          <div className="relative z-[2] flex items-center justify-between gap-4 px-6 pb-2 pt-6 lg:px-10">
            {/* TabsPill */}
            <div
              role="tablist"
              aria-label="Authentication mode"
              className="relative inline-flex h-11 shrink-0 items-center rounded-full border border-white/10 bg-white/5 p-1 backdrop-blur-md"
            >
              {(["signin", "signup"] as AuthMode[]).map((m) => {
                const active = mode === m;
                return (
                  <button
                    key={m}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => setMode(m)}
                    className={`relative z-[1] inline-flex h-9 items-center justify-center whitespace-nowrap rounded-full px-5 text-[13px] font-semibold leading-none tracking-tight transition-colors duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 ${
                      active ? "text-white" : "text-white/60 hover:text-white/85"
                    }`}
                  >
                    {active ? (
                      <motion.span
                        layoutId="authTabUnderline"
                        className="absolute inset-0 -z-[1] rounded-full bg-ss-brand bg-[length:200%_200%] shadow-[0_4px_18px_rgba(124,58,237,0.45)]"
                        transition={{ type: "spring", stiffness: 380, damping: 30 }}
                      />
                    ) : null}
                    <span className="relative">{m === "signin" ? "Sign In" : "Sign Up"}</span>
                  </button>
                );
              })}
            </div>

            {/* BrandMark */}
            <div className="flex shrink-0 items-center gap-2">
              <ShieldMark layoutId={shieldLayoutId} stage="complete" size={28} />
              <span className="hidden text-sm font-semibold tracking-tight text-white sm:inline">
                SmartSpend
              </span>
            </div>
          </div>

          <div className="relative flex flex-1 flex-col justify-center px-5 lg:px-12">
            <div className="relative mx-auto w-full max-w-md">
            {/* Heading */}
            <AnimatePresence mode="wait">
              <motion.div
                key={mode}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.4, ease: BRAND_EASE }}
              >
                <h1 className="mt-8 font-heading text-[clamp(1.55rem,4vw,2.1rem)] font-semibold leading-[1.1] tracking-tight text-white lg:mt-10">
                  {mode === "signin" ? "Welcome back." : "Create your shield."}
                </h1>
                <p className="mt-2 text-[14.5px] leading-relaxed text-ss-mute">
                  {mode === "signin"
                    ? "Pick up where you left off. Your money is safe."
                    : "30-second sign-up. No card. No spam."}
                </p>
              </motion.div>
            </AnimatePresence>

            {/* Error */}
            <AnimatePresence>
              {error ? (
                <motion.div
                  key="auth-err"
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  className="mt-5 rounded-2xl border border-red-400/35 bg-red-500/[0.10] px-4 py-3 text-[13px] text-red-100"
                  role="alert"
                >
                  {error}
                </motion.div>
              ) : null}
            </AnimatePresence>

            {/* Form */}
            <form className="mt-6 space-y-4" onSubmit={submit}>
              <AnimatePresence initial={false}>
                {mode === "signup" ? (
                  <motion.div
                    key="name"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.35, ease: BRAND_EASE }}
                  >
                    <FloatingInput
                      id="auth-name"
                      label="Full name"
                      type="text"
                      autoComplete="name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      required
                    />
                  </motion.div>
                ) : null}
              </AnimatePresence>

              <FloatingInput
                id="auth-email"
                label="Email address"
                type="text"
                inputMode="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />

              <div>
                <FloatingInput
                  id="auth-password"
                  label="Password"
                  type={showPwd ? "text" : "password"}
                  autoComplete={mode === "signin" ? "current-password" : "new-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  trailing={
                    <button
                      type="button"
                      onClick={() => setShowPwd((v) => !v)}
                      aria-label={showPwd ? "Hide password" : "Show password"}
                      className="grid h-9 w-9 place-items-center rounded-full border-0 text-white/60 transition hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                    >
                      {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  }
                />
                {mode === "signup" ? <StrengthMeter password={password} /> : null}
              </div>

              {/* Submit (morphs on click) */}
              <div className="pt-2">
                <MorphSubmit
                  busy={busy}
                  success={success}
                  label={submitLabel}
                  disabled={busy || success}
                />
              </div>

              {/* Legal */}
              <p className="pt-1 text-center text-[11px] leading-relaxed text-white/45">
                By continuing you agree to the{" "}
                <button
                  type="button"
                  className="cursor-pointer border-0 bg-transparent p-0 font-inherit text-inherit underline-offset-2 hover:text-white/80 hover:underline"
                >
                  Terms
                </button>{" "}
                and{" "}
                <button
                  type="button"
                  className="cursor-pointer border-0 bg-transparent p-0 font-inherit text-inherit underline-offset-2 hover:text-white/80 hover:underline"
                >
                  Privacy Policy
                </button>
                .
              </p>
            </form>

            {/* Divider */}
            <div className="my-7 flex items-center gap-3 text-[10px] font-semibold uppercase tracking-[0.22em] text-white/40">
              <span className="h-px flex-1 bg-white/10" />
              or continue with
              <span className="h-px flex-1 bg-white/10" />
            </div>

            {/* Social row */}
            <div className="flex items-center justify-center gap-4">
              <SocialBtn icon={<GoogleGlyph />} label="Continue with Google" />
              <SocialBtn icon={<Apple size={20} />} label="Continue with Apple" />
              <SocialBtn icon={<Github size={20} />} label="Continue with GitHub" />
            </div>

            {/* Switch tab link */}
            <p className="mt-7 text-center text-[13px] text-white/55">
              {mode === "signin" ? (
                <>
                  New to SmartSpend?{" "}
                  <button
                    type="button"
                    onClick={() => setMode("signup")}
                    className="font-semibold text-cyan-300 transition hover:text-cyan-200 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                  >
                    Create an account
                  </button>
                </>
              ) : (
                <>
                  Already have an account?{" "}
                  <button
                    type="button"
                    onClick={() => setMode("signin")}
                    className="font-semibold text-cyan-300 transition hover:text-cyan-200 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                  >
                    Sign in
                  </button>
                </>
              )}
            </p>
            </div>
          </div>

          {/* Mobile sticky CTA mirror (only when CTA isn't already visible) */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 lg:hidden">
            <div className="bg-gradient-to-t from-[#070418] via-[#070418]/85 to-transparent px-5 pb-5 pt-10">
              <p className="text-center text-[10.5px] font-semibold uppercase tracking-[0.18em] text-white/45">
                <ShieldCheck size={11} className="mr-1 inline-block -translate-y-px text-cyan-300" />
                256-bit encryption · RBI aligned
              </p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function GoogleGlyph() {
  // Inline mark — no extra dep needed
  return (
    <svg width={20} height={20} viewBox="0 0 24 24" aria-hidden>
      <path fill="#FFC107" d="M21.6 12.23c0-.74-.07-1.46-.19-2.16H12v4.09h5.4c-.23 1.25-.94 2.31-2 3.02v2.51h3.23c1.89-1.74 2.97-4.31 2.97-7.46z"/>
      <path fill="#4CAF50" d="M12 22c2.7 0 4.96-.9 6.61-2.43l-3.23-2.51c-.9.6-2.04.96-3.38.96-2.6 0-4.8-1.76-5.59-4.13H3.07v2.6A9.99 9.99 0 0 0 12 22z"/>
      <path fill="#FF3D00" d="M6.41 13.89A6 6 0 0 1 6 12c0-.66.11-1.3.31-1.89V7.51H3.07A9.97 9.97 0 0 0 2 12c0 1.6.38 3.11 1.07 4.49l3.34-2.6z"/>
      <path fill="#1976D2" d="M12 6.18c1.47 0 2.79.51 3.83 1.5l2.86-2.86C16.95 3.18 14.7 2.27 12 2.27a9.99 9.99 0 0 0-8.93 5.24l3.34 2.6C7.2 7.94 9.4 6.18 12 6.18z"/>
    </svg>
  );
}

/* ============================ Morphing submit ============================ */

function MorphSubmit({
  busy,
  success,
  label,
  disabled,
}: {
  busy: boolean;
  success: boolean;
  label: string;
  disabled?: boolean;
}) {
  const reduce = useReducedMotion();
  // Three states: idle (pill) / busy (spinning shield) / success (check burst)
  const state = success ? "success" : busy ? "busy" : "idle";

  return (
    <div className="relative h-[58px] w-full">
      <AnimatePresence mode="wait">
        {state === "idle" ? (
          <motion.button
            key="idle"
            type="submit"
            disabled={disabled}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.35, ease: BRAND_EASE }}
            whileHover={reduce || disabled ? undefined : { y: -2 }}
            whileTap={reduce || disabled ? undefined : { scale: 0.98 }}
            className="group relative flex h-full w-full items-center justify-center overflow-hidden rounded-2xl bg-ss-brand bg-[length:220%_220%] text-base font-semibold text-white shadow-ss-cta transition-all duration-500 ease-brand hover:shadow-ss-cta-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[#070418] disabled:cursor-not-allowed disabled:opacity-60"
            style={{ backgroundPosition: "0% 50%" }}
          >
            <span
              className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/25 to-transparent opacity-0 transition duration-700 ease-brand group-hover:translate-x-full group-hover:opacity-100"
              aria-hidden
            />
            <span className="relative flex items-center gap-2">
              {label}
              <ArrowRight size={18} />
            </span>
          </motion.button>
        ) : null}

        {state === "busy" ? (
          <motion.div
            key="busy"
            initial={{ opacity: 0, scale: 0.85 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.85 }}
            transition={{ duration: 0.4, ease: BRAND_EASE }}
            className="absolute inset-0 flex items-center justify-center"
          >
            <motion.div
              className="flex h-14 w-14 items-center justify-center rounded-full bg-ss-brand bg-[length:220%_220%] shadow-ss-cta"
              animate={reduce ? undefined : { rotate: 360 }}
              transition={{ duration: 1.2, repeat: Infinity, ease: "linear" }}
            >
              <ShieldMark stage="complete" size={36} />
            </motion.div>
          </motion.div>
        ) : null}

        {state === "success" ? (
          <motion.div
            key="success"
            initial={{ opacity: 0, scale: 0.4 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.45, ease: BRAND_EASE }}
            className="absolute inset-0 flex items-center justify-center"
          >
            <motion.div
              className="relative flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/95 text-white shadow-[0_0_42px_rgba(16,185,129,0.55)]"
              initial={{ scale: 0.6 }}
              animate={{ scale: [0.6, 1.18, 1] }}
              transition={{ duration: 0.55, ease: BRAND_EASE }}
            >
              <Check size={24} strokeWidth={3} />
              {/* Burst ring */}
              <motion.span
                className="absolute inset-0 rounded-full border-2 border-emerald-300/70"
                initial={{ scale: 0.8, opacity: 0.7 }}
                animate={{ scale: 2.4, opacity: 0 }}
                transition={{ duration: 0.85, ease: BRAND_EASE }}
              />
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

export default IntroAuth;
