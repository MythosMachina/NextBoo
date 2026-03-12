"use client";

import { FormEvent, useState } from "react";
import { fetchCurrentUser, storeTokens, storeUser, useAuthState } from "../components/auth";
import { getBrowserApiBaseUrl } from "../lib/public-api";

export default function InviteRedeemPage() {
  const { setSession } = useAuthState();
  const [form, setForm] = useState({
    code: "",
    email: "",
    username: "",
    password: "",
    confirmPassword: ""
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (form.password !== form.confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    setError(null);

    const response = await fetch(`${getBrowserApiBaseUrl()}/api/v1/invites/redeem`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: form.code,
        email: form.email,
        username: form.username,
        password: form.password
      })
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setLoading(false);
      setError(payload?.detail ?? "Invite redemption failed.");
      return;
    }

    const payload = await response.json();
    storeTokens(payload.data.access_token, payload.data.refresh_token);
    const user = await fetchCurrentUser(payload.data.access_token);
    if (user) {
      storeUser(user);
      setSession(user);
    }
    window.location.href = "/account";
  }

  return (
    <section className="form-panel panel narrow-panel">
      <h2>Redeem Invite</h2>
      <form className="stack-form" onSubmit={handleSubmit}>
        <label>
          Invite code
          <input onChange={(event) => setForm((current) => ({ ...current, code: event.target.value }))} type="text" value={form.code} />
        </label>
        <label>
          Email
          <input onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} type="email" value={form.email} />
        </label>
        <label>
          Username
          <input onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))} type="text" value={form.username} />
        </label>
        <label>
          Password
          <input onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))} type="password" value={form.password} />
        </label>
        <label>
          Confirm password
          <input onChange={(event) => setForm((current) => ({ ...current, confirmPassword: event.target.value }))} type="password" value={form.confirmPassword} />
        </label>
        <button className="primary-button" disabled={loading} type="submit">
          {loading ? "Creating account..." : "Create account"}
        </button>
        {error ? <p className="form-error">{error}</p> : null}
      </form>
    </section>
  );
}
