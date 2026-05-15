/**
 * Sign up — multi-step: account → link bank vs add later → (optional) bank picker.
 */
import { motion, useReducedMotion } from "framer-motion";
import { FormEvent, useEffect, useState } from "react";
import { AuthPageLayout } from "../../../components/Auth/AuthPageLayout";
import { useAuth } from "../../../context/AuthContext";
import { onboardingGetBanks } from "../../../services/api";

const inputClass =
  "w-full min-h-[54px] rounded-xl border border-white/[0.1] bg-white/[0.07] px-4 py-3 text-[15px] text-white shadow-[inset_0_2px_6px_rgba(0,0,0,0.28),inset_0_1px_0_rgba(255,255,255,0.06)] outline-none transition-all duration-300 ease-out placeholder:text-slate-500 hover:border-white/[0.16] hover:bg-white/[0.1] focus:border-violet-400/50 focus:shadow-[inset_0_2px_8px_rgba(0,0,0,0.22),0_0_0_4px_rgba(168,85,247,0.14),0_0_32px_rgba(139,92,246,0.2),0_0_22px_rgba(6,182,212,0.1)] md:min-h-[56px]";

const labelClass =
  "mb-1 block text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400";

const Spinner = () => (
  <span className="inline-flex items-center justify-center gap-2">
    <svg className="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
      <path
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        className="opacity-90"
      />
    </svg>
    Creating account…
  </span>
);

export interface SignUpPageProps {
  onSwitchToSignin: () => void;
}

type Step = 1 | 2 | 3;

export default function SignUpPage({ onSwitchToSignin }: SignUpPageProps) {
  const reduce = useReducedMotion();
  const { signup } = useAuth();
  const [step, setStep] = useState<Step>(1);
  const [connection, setConnection] = useState<"link_bank" | "add_later" | null>(null);
  const [banks, setBanks] = useState<Array<{ id: string; name: string; logo?: string }>>([]);
  const [selectedBank, setSelectedBank] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (step !== 3 || connection !== "link_bank") return;
    let cancelled = false;
    onboardingGetBanks()
      .then((d) => {
        if (!cancelled) setBanks(Array.isArray(d?.banks) ? d.banks : []);
      })
      .catch(() => {
        if (!cancelled) setBanks([]);
      });
    return () => {
      cancelled = true;
    };
  }, [step, connection]);

  const submitBasics = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError("");
    setStep(2);
  };

  const chooseLinkBank = () => {
    setConnection("link_bank");
    setStep(3);
  };

  const chooseAddLater = async () => {
    setConnection("add_later");
    setBusy(true);
    setError("");
    try {
      await signup({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
        signup_connection: "add_later",
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Sign up failed";
      setError(msg);
      setStep(1);
      setConnection(null);
    } finally {
      setBusy(false);
    }
  };

  const finishWithBank = async () => {
    if (!selectedBank) {
      setError("Pick a bank to continue.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await signup({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
        signup_connection: "link_bank",
        primary_bank: selectedBank,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Sign up failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  const title =
    step === 1 ? "Create account" : step === 2 ? "Connect your data" : "Choose your bank";

  const lead =
    step === 1
      ? "Start managing your finances intelligently."
      : step === 2
        ? "Upload-based only — no live bank API sync. Pick how you want to begin."
        : "We will tag your demo workspace with this bank. You can add cards or statements later in Settings.";

  return (
    <AuthPageLayout
      cardTitle={title}
      cardLead={lead}
      error={error}
      footer={
        <p className="text-center text-sm text-slate-500">
          {step > 1 ? (
            <button
              type="button"
              className="font-semibold text-violet-400 underline-offset-2 transition hover:text-fuchsia-400 hover:underline"
              onClick={() => {
                setError("");
                if (step === 3) {
                  setStep(2);
                  setSelectedBank(null);
                } else setStep(1);
              }}
            >
              Back
            </button>
          ) : null}
          {step > 1 ? <span className="text-slate-600"> · </span> : null}
          Already registered?{" "}
          <button
            type="button"
            className="font-semibold text-violet-400 underline-offset-2 transition hover:text-fuchsia-400 hover:underline"
            onClick={onSwitchToSignin}
          >
            Sign in
          </button>
        </p>
      }
    >
      {step === 1 ? (
        <form className="space-y-3.5" onSubmit={submitBasics}>
          <div>
            <label className={labelClass} htmlFor="su-name">
              Full name
            </label>
            <input
              id="su-name"
              className={inputClass}
              placeholder="John Doe"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              minLength={2}
              required
              autoComplete="name"
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="su-email">
              Email
            </label>
            <input
              id="su-email"
              className={inputClass}
              type="text"
              inputMode="email"
              placeholder="john@example.com"
              autoComplete="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="su-pass">
              Password (min 8)
            </label>
            <input
              id="su-pass"
              className={inputClass}
              type="password"
              placeholder="••••••••"
              autoComplete="new-password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              minLength={8}
              required
            />
          </div>
          <motion.button
            type="submit"
            whileTap={reduce ? undefined : { scale: 0.98 }}
            whileHover={reduce ? undefined : { y: -2 }}
            transition={{ type: "spring", stiffness: 400, damping: 24 }}
            className="group relative mt-2 flex min-h-[58px] w-full items-center justify-center overflow-hidden rounded-xl bg-gradient-to-r from-violet-600 via-fuchsia-600 to-pink-600 text-base font-semibold text-white shadow-[0_16px_48px_rgba(139,92,246,0.45)] transition-all duration-300 ease-out"
          >
            Continue
          </motion.button>
        </form>
      ) : null}

      {step === 2 ? (
        <div className="space-y-4">
          <button
            type="button"
            onClick={chooseLinkBank}
            className="flex w-full flex-col rounded-2xl border border-white/10 bg-white/[0.06] p-4 text-left transition hover:border-violet-500/40 hover:bg-white/[0.09]"
          >
            <span className="text-2xl">🏦</span>
            <span className="mt-2 text-base font-semibold text-white">Link bank (demo)</span>
            <span className="mt-1 text-sm text-slate-400">
              Choose your bank for a fuller dashboard (salary, rent, savings context). Still upload-based — no live
              sync.
            </span>
          </button>
          <button
            type="button"
            onClick={chooseAddLater}
            disabled={busy}
            className="flex w-full flex-col rounded-2xl border border-white/10 bg-white/[0.04] p-4 text-left transition hover:border-cyan-500/35 hover:bg-cyan-500/10 disabled:opacity-50"
          >
            <span className="text-2xl">💳</span>
            <span className="mt-2 text-base font-semibold text-white">Credit card / statements — add later</span>
            <span className="mt-1 text-sm text-slate-400">
              Skip for now. After sign-in, go to Settings → Connected accounts to upload PDF/CSV statements.
            </span>
            {busy ? <span className="mt-3 text-sm text-violet-300">Working…</span> : null}
          </button>
        </div>
      ) : null}

      {step === 3 && connection === "link_bank" ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {banks.map((b) => (
              <button
                key={b.id}
                type="button"
                onClick={() => setSelectedBank(b.name)}
                className={`rounded-xl border px-3 py-3 text-left text-sm font-medium transition ${
                  selectedBank === b.name
                    ? "border-violet-500 bg-violet-600/25 text-white"
                    : "border-white/10 bg-white/[0.05] text-slate-200 hover:border-white/20"
                }`}
              >
                <span className="mr-2">{b.logo ?? "🏦"}</span>
                {b.name}
              </button>
            ))}
          </div>
          <motion.button
            type="button"
            disabled={busy || !selectedBank}
            onClick={finishWithBank}
            whileTap={reduce || busy ? undefined : { scale: 0.98 }}
            className="flex min-h-[54px] w-full items-center justify-center rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-base font-semibold text-white disabled:cursor-not-allowed disabled:opacity-45"
          >
            {busy ? <Spinner /> : "Create account"}
          </motion.button>
        </div>
      ) : null}
    </AuthPageLayout>
  );
}
