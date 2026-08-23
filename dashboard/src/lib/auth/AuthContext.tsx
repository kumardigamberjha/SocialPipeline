"use client";

/**
 * Session state for the whole dashboard.
 *
 * Bootstraps from `GET /api/auth/me` on mount (the cookie, if any, is sent
 * automatically). There is no token anywhere in this file — the browser
 * carries the session via httpOnly cookies, and this context only tracks
 * *whether* one is live, never a credential itself.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { ApiError, request, trySilentRefresh } from "@/lib/apiClient";

export interface SessionUser {
  id: string;
  email: string;
  created_at: string;
}

interface AuthContextValue {
  user: SessionUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  /** Returns the registered email so the caller can show the OTP step. */
  signup: (email: string, password: string) => Promise<{ email: string }>;
  verifyEmail: (email: string, otp: string) => Promise<void>;
  resendOtp: (email: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  setUser: (user: SessionUser | null) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);

  const bootstrap = useCallback(async () => {
    try {
      // A 401 here is a normal, expected "not signed in" — never send this
      // through the apiClient's refresh/redirect cycle, or a fresh visitor
      // gets bounced through /login before they've done anything.
      const data = await request<{ user: SessionUser }>("/auth/me", {
        skipAuthRetry: true,
      });
      setUser(data.user);
    } catch {
      // The access token is short-lived (15 min) and expires constantly just
      // from a tab sitting in the background — that alone isn't "logged out"
      // as long as the 30-day refresh cookie is still valid. Try one silent
      // refresh before concluding there's no session, so returning to a tab
      // doesn't bounce a still-valid session to the login screen.
      try {
        const refreshed = await trySilentRefresh();
        if (refreshed) {
          const data = await request<{ user: SessionUser }>("/auth/me", {
            skipAuthRetry: true,
          });
          setUser(data.user);
          return;
        }
      } catch {
        /* fall through to logged-out */
      }
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  const login = useCallback(async (email: string, password: string) => {
    const data = await request<{ user: SessionUser }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
      skipAuthRetry: true,
    });
    setUser(data.user);
  }, []);

  /**
   * Register a new account.
   * Returns { email } — does NOT set the user or issue a session.
   * The caller should show an OTP entry step next.
   */
  const signup = useCallback(
    async (email: string, password: string): Promise<{ email: string }> => {
      const data = await request<{ email: string; message: string }>(
        "/auth/register",
        {
          method: "POST",
          body: JSON.stringify({ email, password }),
          skipAuthRetry: true,
        }
      );
      return { email: data.email };
    },
    []
  );

  /** Submit the OTP received by email. On success sets the user (session issued). */
  const verifyEmail = useCallback(async (email: string, otp: string) => {
    const data = await request<{ user: SessionUser }>("/auth/verify-email", {
      method: "POST",
      body: JSON.stringify({ email, otp }),
      skipAuthRetry: true,
    });
    setUser(data.user);
  }, []);

  /** Request a fresh OTP for the given email. */
  const resendOtp = useCallback(async (email: string) => {
    await request("/auth/resend-otp", {
      method: "POST",
      body: JSON.stringify({ email }),
      skipAuthRetry: true,
    });
  }, []);

  const logout = useCallback(async () => {
    try {
      await request("/auth/logout", { method: "POST", skipAuthRetry: true });
    } catch (err) {
      // Cookies may already be gone (e.g. expired) — that is still "logged
      // out" from the UI's perspective, so swallow anything but a genuine
      // network failure.
      if (!(err instanceof ApiError)) throw err;
    } finally {
      setUser(null);
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        signup,
        verifyEmail,
        resendOtp,
        logout,
        refresh: bootstrap,
        setUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
