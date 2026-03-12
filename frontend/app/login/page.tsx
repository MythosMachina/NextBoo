"use client";

import { FormEvent, useState } from "react";
import { fetchCurrentUser, storeTokens, storeUser, useAuthState } from "../components/auth";
import { getBrowserApiBaseUrl } from "../lib/public-api";

export default function LoginPage() {
  const { setSession } = useAuthState();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    const body = new URLSearchParams({ username, password });
    const response = await fetch(`${getBrowserApiBaseUrl()}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body
    });

    if (!response.ok) {
      setLoading(false);
      setError("Login failed.");
      return;
    }

    const payload = await response.json();
    storeTokens(payload.data.access_token, payload.data.refresh_token);
    const user = await fetchCurrentUser(payload.data.access_token);
    if (user) {
      storeUser(user);
      setSession(user);
    }
    window.location.href = user?.role === "admin" || user?.role === "moderator" ? "/admin" : "/account";
  }

  return (
    <section className="form-panel panel narrow-panel">
      <h2>Login</h2>
      <form className="stack-form" onSubmit={handleSubmit}>
        <label>
          Username
          <input onChange={(event) => setUsername(event.target.value)} type="text" value={username} />
        </label>
        <label>
          Password
          <input onChange={(event) => setPassword(event.target.value)} type="password" value={password} />
        </label>
        <button className="primary-button" disabled={loading} type="submit">
          {loading ? "Signing in..." : "Login"}
        </button>
        {error ? <p className="form-error">{error}</p> : null}
      </form>
      <p className="form-help">
        No public registration. Use an invite link or code to create an account.
        {" "}
        <a href="/invite">Redeem invite</a>
      </p>
    </section>
  );
}
