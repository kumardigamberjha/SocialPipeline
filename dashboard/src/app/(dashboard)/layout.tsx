"use client";

/**
 * Shared chrome for the analysis pages (youtube-analysis, instagram-analysis,
 * planner-analysis). This route group previously had no layout.tsx at all —
 * each page hand-rolled its own <Header>/<footer> pair, which is where the
 * copy-pasted footer markup came from.
 *
 * Also the auth guard for this group: `middleware.ts` already redirects a
 * signed-out visitor to /login based on cookie presence, but that is a
 * same-request redirect and doesn't cover the case where a session expires
 * *while the page is open*. This re-checks client-side once the auth
 * bootstrap resolves and bounces if there's no user.
 */

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import Footer from "@/components/Footer";
import Header from "@/components/Header";
import { useAuth } from "@/lib/auth/AuthContext";

export default function DashboardGroupLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-slate-500">Loading…</p>
      </main>
    );
  }

  return (
    <main className="flex flex-col min-h-screen">
      <Header />
      <div className="flex-1 flex flex-col py-8 sm:py-10 overflow-hidden">{children}</div>
      <Footer />
    </main>
  );
}
