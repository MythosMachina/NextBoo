"use client";

import Link from "next/link";
import { useAuthState } from "./auth";

export function AuthStatus() {
  const { authenticated, isAdmin, isModerator, clearSession, user } = useAuthState();

  function handleLogout() {
    clearSession();
    window.location.href = "/";
  }

  if (authenticated) {
    return (
      <div className="auth-status">
        {isAdmin ? <Link href="/admin">Admin</Link> : null}
        {!isAdmin && isModerator ? <Link href="/admin">Moderation</Link> : null}
        <span className="auth-user">{user?.username}</span>
        <button className="theme-toggle" onClick={handleLogout} type="button">
          Logout
        </button>
      </div>
    );
  }

  return (
    <div className="auth-status">
      <Link href="/login">Login</Link>
    </div>
  );
}
