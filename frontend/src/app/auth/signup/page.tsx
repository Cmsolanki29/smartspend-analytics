/**
 * Sign up — same split shell as sign-in (CRA: `components/Auth/SignUp.jsx` re-export).
 */
import { motion, useReducedMotion } from "framer-motion";
import { FormEvent, useState } from "react";
import { AuthPageLayout } from "../../../components/Auth/AuthPageLayout";
import { useAuth } from "../../../context/AuthContext";

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

export default function SignUpPage({ onSwitchToSignin }: SignUpPageProps) {
  const reduce = useReducedMotion();
  const { signup } = useAuth();
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await signup({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Sign up failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthPageLayout
      cardTitle="Create Account"
      cardLead="Start managing your finances intelligently."
      error={error}
      footer={
        <p className="text-center text-sm text-slate-500">
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
      <form className="space-y-3.5" onSubmit={submit}>
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
          disabled={busy}
          whileTap={reduce || busy ? undefined : { scale: 0.98 }}
          whileHover={reduce || busy ? undefined : { y: -2 }}
          transition={{ type: "spring", stiffness: 400, damping: 24 }}
          className="group relative mt-2 flex min-h-[58px] w-full items-center justify-center overflow-hidden rounded-xl bg-gradient-to-r from-violet-600 via-fuchsia-600 to-pink-600 text-base font-semibold text-white shadow-[0_16px_48px_rgba(139,92,246,0.45),0_0_32px_rgba(236,72,153,0.2)] transition-all duration-300 ease-out hover:shadow-[0_22px_56px_rgba(139,92,246,0.55),0_0_40px_rgba(6,182,212,0.15)] disabled:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none"
        >
          <span
            className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/20 to-transparent opacity-0 transition duration-700 group-hover:translate-x-full group-hover:opacity-100"
            aria-hidden
          />
          {busy ? <Spinner /> : "Sign up"}
        </motion.button>
      </form>
    </AuthPageLayout>
  );
}
