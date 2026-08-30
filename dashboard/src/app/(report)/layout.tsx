"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth/AuthContext";

/**
 * Bare shell for shareable reports — no Sidebar, TopBar or Footer.
 *
 * Its whole reason to exist is the screenshot: the dashboard chrome would end
 * up in every captured panel and every printed page. Auth still gates it (the
 * report contains the user's own generated analysis), it just renders nothing
 * around the content.
 */
export default function ReportGroupLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
      </main>
    );
  }

  return <div className="min-h-screen bg-slate-950 text-slate-200 print:bg-white print:text-slate-900">{children}</div>;
}
