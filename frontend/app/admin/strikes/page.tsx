"use client";

import { FormEvent, useEffect, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch, useAuthState } from "../../components/auth";

type Strike = {
  id: number;
  target_username: string;
  issued_by_username: string | null;
  related_username: string | null;
  source: "manual" | "invitee_ban" | "threshold_auto_ban";
  reason: string;
  created_at: string;
};

export default function AdminStrikesPage() {
  const { isAdmin, isModerator } = useAuthState();
  const [strikes, setStrikes] = useState<Strike[]>([]);
  const [form, setForm] = useState({ username: "", reason: "" });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function loadStrikes() {
    if (!isAdmin && !isModerator) {
      setLoading(false);
      return;
    }
    const response = await authFetch("/api/v1/strikes");
    if (!response.ok) {
      setLoading(false);
      setError("Failed to load strikes.");
      return;
    }
    const payload = await response.json();
    setStrikes(payload.data);
    setLoading(false);
  }

  useEffect(() => {
    loadStrikes();
  }, [isAdmin, isModerator]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);
    const response = await authFetch("/api/v1/strikes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form)
    });
    setSaving(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? "Failed to issue strike.");
      return;
    }
    setForm({ username: "", reason: "" });
    setSuccess("Strike issued.");
    await loadStrikes();
  }

  async function handleBan() {
    setSaving(true);
    setError(null);
    setSuccess(null);
    const response = await authFetch("/api/v1/strikes/ban", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form)
    });
    setSaving(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? "Failed to ban user.");
      return;
    }
    setForm({ username: "", reason: "" });
    setSuccess("User banned.");
    await loadStrikes();
  }

  return (
    <AdminShell title="Strikes" description="Manual strike control and social-gate enforcement history.">
      <section className="panel">
        <h2>Issue Strike</h2>
        <form className="stack-form narrow-panel" onSubmit={handleSubmit}>
          <label>
            Username
            <input onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))} type="text" value={form.username} />
          </label>
          <label>
            Reason
            <textarea className="stack-textarea" onChange={(event) => setForm((current) => ({ ...current, reason: event.target.value }))} rows={4} value={form.reason} />
          </label>
          <button className="danger-button" disabled={saving} type="submit">
            {saving ? "Issuing..." : "Issue strike"}
          </button>
          <button className="theme-toggle" disabled={saving} onClick={handleBan} type="button">
            {saving ? "Working..." : "Ban user"}
          </button>
          {error ? <p className="form-error">{error}</p> : null}
          {success ? <p className="form-success">{success}</p> : null}
        </form>
      </section>

      <section className="panel">
        <h2>Strike Log</h2>
        {loading ? (
          <div className="empty-state compact-empty">
            <strong>Loading strikes.</strong>
            <p>Fetching social-gate history.</p>
          </div>
        ) : strikes.length ? (
          <div className="table-wrap">
            <table className="simple-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Source</th>
                  <th>Actor</th>
                  <th>Related</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {strikes.map((strike) => (
                  <tr key={strike.id}>
                    <td>{strike.target_username}</td>
                    <td>{strike.source}</td>
                    <td>{strike.issued_by_username ?? "-"}</td>
                    <td>{strike.related_username ?? "-"}</td>
                    <td>{strike.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state compact-empty">
            <strong>No strikes recorded.</strong>
            <p>Manual and invite-chain sanctions will appear here.</p>
          </div>
        )}
      </section>
    </AdminShell>
  );
}
