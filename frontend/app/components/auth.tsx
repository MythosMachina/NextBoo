"use client";

import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { getBrowserApiBaseUrl } from "../lib/public-api";

const ACCESS_TOKEN_KEY = "nextboo-access-token";
const REFRESH_TOKEN_KEY = "nextboo-refresh-token";
const USER_KEY = "nextboo-user";
const AUTH_EVENT_NAME = "nextboo-auth-changed";
let refreshPromise: Promise<string | null> | null = null;

export type SessionUser = {
  id: number;
  username: string;
  email: string | null;
  role: "admin" | "moderator" | "uploader";
  is_active: boolean;
  can_upload: boolean;
  invite_quota: number;
  invite_slots_used: number;
  invite_slots_remaining: number;
  invited_by_username: string | null;
  strike_count: number;
  can_view_questionable: boolean;
  can_view_explicit: boolean;
  tag_blacklist: string[];
};

type AuthContextValue = {
  authenticated: boolean;
  loading: boolean;
  user: SessionUser | null;
  isAdmin: boolean;
  isModerator: boolean;
  isStaff: boolean;
  canUpload: boolean;
  setSession: (user: SessionUser | null) => void;
  clearSession: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function emitAuthChanged(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.dispatchEvent(new CustomEvent(AUTH_EVENT_NAME));
}

export function getStoredAccessToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getStoredRefreshToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function storeTokens(accessToken: string, refreshToken: string): void {
  window.localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  window.localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  emitAuthChanged();
}

export function getStoredUser(): SessionUser | null {
  if (typeof window === "undefined") {
    return null;
  }
  const rawValue = window.localStorage.getItem(USER_KEY);
  if (!rawValue) {
    return null;
  }
  try {
    return JSON.parse(rawValue) as SessionUser;
  } catch {
    return null;
  }
}

export function storeUser(user: SessionUser): void {
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  emitAuthChanged();
}

export function clearTokens(): void {
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
  emitAuthChanged();
}

export async function refreshTokens(): Promise<string | null> {
  if (refreshPromise) {
    return refreshPromise;
  }

  const refreshToken = getStoredRefreshToken();
  if (!refreshToken) {
    clearTokens();
    return null;
  }

  refreshPromise = (async () => {
    const response = await fetch(`${getBrowserApiBaseUrl()}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken })
    });
    if (!response.ok) {
      clearTokens();
      return null;
    }

    const payload = await response.json();
    storeTokens(payload.data.access_token, payload.data.refresh_token);
    return payload.data.access_token as string;
  })();

  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  let accessToken = getStoredAccessToken();
  const perform = (token: string | null) => {
    const headers = new Headers(init.headers ?? {});
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    return fetch(`${getBrowserApiBaseUrl()}${path}`, { ...init, headers });
  };

  let response = await perform(accessToken);
  if (response.status !== 401) {
    return response;
  }

  accessToken = await refreshTokens();
  if (!accessToken) {
    return response;
  }

  response = await perform(accessToken);
  return response;
}

export async function fetchCurrentUser(_accessToken?: string | null): Promise<SessionUser | null> {
  const response = await authFetch("/api/v1/auth/me");
  if (!response.ok) {
    return null;
  }
  const payload = await response.json();
  return payload.data as SessionUser;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(false);
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function resolveSession() {
      let token = getStoredAccessToken();
      const storedUser = getStoredUser();
      if (!token) {
        setAuthenticated(false);
        setUser(null);
        setLoading(false);
        return;
      }

      let nextUser = await fetchCurrentUser(token);
      if (!nextUser) {
        token = await refreshTokens();
        if (token) {
          nextUser = await fetchCurrentUser(token);
        }
      }

      if (!nextUser) {
        clearTokens();
        setAuthenticated(false);
        setUser(null);
        setLoading(false);
        return;
      }

      storeUser(nextUser);
      setAuthenticated(true);
      setUser(nextUser ?? storedUser);
      setLoading(false);
    }

    resolveSession();
    function handleAuthChanged() {
      const token = getStoredAccessToken();
      const storedUser = getStoredUser();
      setAuthenticated(Boolean(token && storedUser));
      setUser(storedUser);
      setLoading(false);
    }

    window.addEventListener(AUTH_EVENT_NAME, handleAuthChanged);
    window.addEventListener("storage", handleAuthChanged);

    return () => {
      window.removeEventListener(AUTH_EVENT_NAME, handleAuthChanged);
      window.removeEventListener("storage", handleAuthChanged);
    };
  }, []);

  function setSession(nextUser: SessionUser | null) {
    if (nextUser) {
      storeUser(nextUser);
    } else {
      clearTokens();
    }
    setAuthenticated(Boolean(nextUser));
    setUser(nextUser);
  }

  function clearSession() {
    clearTokens();
    setAuthenticated(false);
    setUser(null);
  }

  return (
    <AuthContext.Provider
      value={{
        authenticated,
        loading,
        user,
        isAdmin: user?.role === "admin",
        isModerator: user?.role === "moderator",
        isStaff: user?.role === "admin" || user?.role === "moderator",
        canUpload: Boolean(user?.can_upload || user?.role === "admin" || user?.role === "moderator"),
        setSession,
        clearSession
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuthState() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuthState must be used within AuthProvider");
  }
  return context;
}
