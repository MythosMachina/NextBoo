"use client";

import { FormEvent, useEffect, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type RateLimitSettings = {
  rate_limit_login_max_requests: number;
  rate_limit_login_window_seconds: number;
  rate_limit_search_max_requests: number;
  rate_limit_search_window_seconds: number;
  rate_limit_upload_max_requests: number;
  rate_limit_upload_window_seconds: number;
  rate_limit_admin_write_max_requests: number;
  rate_limit_admin_write_window_seconds: number;
};

const DEFAULT_SETTINGS: RateLimitSettings = {
  rate_limit_login_max_requests: 5,
  rate_limit_login_window_seconds: 60,
  rate_limit_search_max_requests: 120,
  rate_limit_search_window_seconds: 60,
  rate_limit_upload_max_requests: 30,
  rate_limit_upload_window_seconds: 600,
  rate_limit_admin_write_max_requests: 60,
  rate_limit_admin_write_window_seconds: 60,
};

function numberValue(rawValue: string): number {
  return Math.max(Number.parseInt(rawValue || "1", 10) || 1, 1);
}

export default function AdminRateLimitsPage() {
  const [formState, setFormState] = useState<RateLimitSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadSettings() {
      const response = await authFetch("/api/v1/admin/settings/rate-limits");
      if (!response.ok) {
        setError("Failed to load rate limits.");
        setLoading(false);
        return;
      }
      const payload = await response.json();
      setFormState(payload.data);
      setLoading(false);
    }

    loadSettings();
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    setError(null);
    const response = await authFetch("/api/v1/admin/settings/rate-limits", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formState),
    });
    setSaving(false);
    if (!response.ok) {
      setError("Failed to save rate limits.");
      return;
    }
    const payload = await response.json();
    setFormState(payload.data);
    setMessage("Rate limits saved.");
  }

  return (
    <AdminShell
      title="Rate Limits"
      description="Adjust default request ceilings for auth, search, uploads, and sensitive admin writes."
    >
      <section className="panel">
        <h2>Rate Limit Controls</h2>
        {loading ? (
          <div className="empty-state">
            <strong>Loading rate limits.</strong>
            <p>Fetching the active values from the database.</p>
          </div>
        ) : (
          <form className="stack-form" onSubmit={handleSubmit}>
            <label>
              Login max requests
              <input
                min={1}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, rate_limit_login_max_requests: numberValue(event.target.value) }))
                }
                type="number"
                value={formState.rate_limit_login_max_requests}
              />
            </label>
            <label>
              Login window seconds
              <input
                min={1}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, rate_limit_login_window_seconds: numberValue(event.target.value) }))
                }
                type="number"
                value={formState.rate_limit_login_window_seconds}
              />
            </label>
            <label>
              Search max requests
              <input
                min={1}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, rate_limit_search_max_requests: numberValue(event.target.value) }))
                }
                type="number"
                value={formState.rate_limit_search_max_requests}
              />
            </label>
            <label>
              Search window seconds
              <input
                min={1}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, rate_limit_search_window_seconds: numberValue(event.target.value) }))
                }
                type="number"
                value={formState.rate_limit_search_window_seconds}
              />
            </label>
            <label>
              Upload max requests
              <input
                min={1}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, rate_limit_upload_max_requests: numberValue(event.target.value) }))
                }
                type="number"
                value={formState.rate_limit_upload_max_requests}
              />
            </label>
            <label>
              Upload window seconds
              <input
                min={1}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, rate_limit_upload_window_seconds: numberValue(event.target.value) }))
                }
                type="number"
                value={formState.rate_limit_upload_window_seconds}
              />
            </label>
            <label>
              Admin write max requests
              <input
                min={1}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, rate_limit_admin_write_max_requests: numberValue(event.target.value) }))
                }
                type="number"
                value={formState.rate_limit_admin_write_max_requests}
              />
            </label>
            <label>
              Admin write window seconds
              <input
                min={1}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, rate_limit_admin_write_window_seconds: numberValue(event.target.value) }))
                }
                type="number"
                value={formState.rate_limit_admin_write_window_seconds}
              />
            </label>
            <button className="primary-button" disabled={saving} type="submit">
              {saving ? "Saving..." : "Save rate limits"}
            </button>
            {message ? <p className="form-success">{message}</p> : null}
            {error ? <p className="form-error">{error}</p> : null}
          </form>
        )}
      </section>
    </AdminShell>
  );
}
