"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";

import { ApiError } from "@/lib/apiClient";
import { useAuth } from "@/lib/auth/AuthContext";

const MIN_PASSWORD_LENGTH = 12;

type Step = "register" | "verify";

export default function SignupPage() {
  const { signup, verifyEmail, resendOtp } = useAuth();
  const router = useRouter();

  // ── Step 1: Registration ───────────────────────────────────────────────────
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // ── Step 2: OTP verification ───────────────────────────────────────────────
  const [step, setStep] = useState<Step>("register");
  const [otp, setOtp] = useState("");
  const [resent, setResent] = useState(false);

  // ── Shared state ───────────────────────────────────────────────────────────
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const pendingEmail = useRef("");

  // ── Step 1 handler ─────────────────────────────────────────────────────────
  async function onRegister(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }

    setSubmitting(true);
    try {
      const result = await signup(email, password);
      pendingEmail.current = result.email;
      setStep("verify");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Something went wrong. Try again."
      );
    } finally {
      setSubmitting(false);
    }
  }

  // ── Step 2 handler ─────────────────────────────────────────────────────────
  async function onVerify(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await verifyEmail(pendingEmail.current, otp.trim());
      router.replace("/");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Something went wrong. Try again."
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function onResend() {
    setError(null);
    setResent(false);
    try {
      await resendOtp(pendingEmail.current);
      setResent(true);
    } catch {
      setError("Could not resend the code. Try again in a moment.");
    }
  }

  // ── Render: OTP step ───────────────────────────────────────────────────────
  if (step === "verify") {
    return (
      <form
        onSubmit={onVerify}
        className="glass-card space-y-5 rounded-xl border border-white/10 p-6"
      >
        {/* Icon */}
        <div className="flex justify-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-500/20 text-2xl">
            ✉️
          </span>
        </div>

        <div className="text-center">
          <h2 className="text-lg font-semibold text-slate-100">Check your inbox</h2>
          <p className="mt-1 text-sm text-slate-400">
            We sent a 6-digit code to{" "}
            <span className="font-medium text-indigo-300">{pendingEmail.current}</span>.
            Enter it below to activate your account.
          </p>
        </div>

        <div>
          <label htmlFor="otp" className="mb-1 block text-sm font-medium text-slate-300">
            Verification code
          </label>
          <input
            id="otp"
            type="text"
            inputMode="numeric"
            pattern="[0-9]{6}"
            maxLength={6}
            required
            autoFocus
            autoComplete="one-time-code"
            value={otp}
            onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
            placeholder="000000"
            className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-3 text-center text-2xl font-mono tracking-[0.5em] text-slate-100 outline-none focus:border-indigo-400"
          />
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}
        {resent && (
          <p className="text-sm text-emerald-400">
            A new code has been sent — check your inbox.
          </p>
        )}

        <button
          type="submit"
          disabled={submitting || otp.length !== 6}
          className="w-full rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-50"
        >
          {submitting ? "Verifying…" : "Verify email"}
        </button>

        <p className="text-center text-sm text-slate-500">
          Didn&apos;t get the code?{" "}
          <button
            type="button"
            onClick={onResend}
            className="text-indigo-400 hover:text-indigo-300"
          >
            Resend
          </button>
        </p>
      </form>
    );
  }

  // ── Render: Register step ──────────────────────────────────────────────────
  return (
    <form
      onSubmit={onRegister}
      className="glass-card space-y-4 rounded-xl border border-white/10 p-6"
    >
      <div>
        <label htmlFor="email" className="mb-1 block text-sm font-medium text-slate-300">
          Email
        </label>
        <input
          id="email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-400"
        />
      </div>
      <div>
        <label
          htmlFor="password"
          className="mb-1 block text-sm font-medium text-slate-300"
        >
          Password
        </label>
        <input
          id="password"
          type="password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-400"
        />
        <p className="mt-1 text-xs text-slate-500">At least {MIN_PASSWORD_LENGTH} characters.</p>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-50"
      >
        {submitting ? "Creating account…" : "Create account"}
      </button>

      <p className="text-center text-sm text-slate-500">
        Already have an account?{" "}
        <Link href="/login" className="text-indigo-400 hover:text-indigo-300">
          Sign in
        </Link>
      </p>
    </form>
  );
}
