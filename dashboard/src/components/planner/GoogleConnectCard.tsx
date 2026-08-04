"use client";

import { Calendar, CheckCircle2, Loader2, Unlink } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { plannerApi, GoogleStatus } from "@/lib/plannerApi";

export default function GoogleConnectCard() {
  const [status, setStatus] = useState<GoogleStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const searchParams = useSearchParams();

  const refresh = useCallback(async () => {
    try {
      setStatus(await plannerApi.googleStatus());
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh, searchParams]);

  useEffect(() => {
    if (searchParams.get("google") === "error") {
      setError("Google connection failed. Check backend GOOGLE_CLIENT_ID/SECRET and try again.");
    }
  }, [searchParams]);

  const connect = async () => {
    setBusy(true);
    setError(null);
    try {
      const { authorization_url } = await plannerApi.googleAuthorizeUrl();
      window.location.href = authorization_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start Google authorization");
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    setError(null);
    try {
      await plannerApi.googleDisconnect();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Disconnect failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3 flex items-center gap-3 flex-wrap">
      <Calendar className="w-4 h-4 text-blue-400 shrink-0" />
      <div className="flex-1 min-w-[180px]">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-300">Google Calendar</p>
        {status?.connected ? (
          <p className="text-xs text-green-400 flex items-center gap-1 mt-0.5">
            <CheckCircle2 className="w-3 h-3" /> Connected{status.email ? ` as ${status.email}` : ""}
          </p>
        ) : (
          <p className="text-xs text-slate-500 mt-0.5">Connect to add plan items to your calendar with reminders.</p>
        )}
        {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
      </div>
      {status?.connected ? (
        <button
          onClick={disconnect}
          disabled={busy}
          className="text-xs px-3 py-1.5 rounded-lg border border-white/10 text-slate-400 hover:text-red-400 hover:border-red-400/30 transition-colors flex items-center gap-1.5 disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Unlink className="w-3 h-3" />} Disconnect
        </button>
      ) : (
        <button
          onClick={connect}
          disabled={busy}
          className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white transition-colors flex items-center gap-1.5 disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Calendar className="w-3 h-3" />} Connect
        </button>
      )}
    </div>
  );
}
