"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { ApiError } from "@/lib/apiClient";
import { useAuth } from "@/lib/auth/AuthContext";

// useSearchParams() opts this page out of static prerendering unless wrapped
// in Suspense — Next.js requires the boundary so the `next=` redirect target
// can be read client-side without blocking the initial shell.
export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      const next = searchParams.get("next") || "/";
      router.replace(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="glass-card space-y-4 rounded-xl border border-white/10 p-6">
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
        <label htmlFor="password" className="mb-1 block text-sm font-medium text-slate-300">
          Password
        </label>
        <input
          id="password"
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-400"
        />
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-50"
      >
        {submitting ? "Signing in…" : "Sign in"}
      </button>

      <p className="text-center text-sm text-slate-500">
        No account?{" "}
        <Link href="/signup" className="text-indigo-400 hover:text-indigo-300">
          Create one
        </Link>
      </p>
    </form>
  );
}
