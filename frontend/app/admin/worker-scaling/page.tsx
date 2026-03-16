"use client";

import { FormEvent, useEffect, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type AutoscalerSettings = {
  autoscaler_enabled: boolean;
  autoscaler_jobs_per_worker: number;
  autoscaler_min_workers: number;
  autoscaler_max_workers: number;
  autoscaler_poll_seconds: number;
  active_workers: string[];
  current_worker_count: number;
  queue_depth: number;
  recommended_worker_count: number;
  last_scale_action: string | null;
  last_scale_at: string | null;
  last_error: string | null;
};

const DEFAULT_SETTINGS: AutoscalerSettings = {
  autoscaler_enabled: false,
  autoscaler_jobs_per_worker: 100,
  autoscaler_min_workers: 1,
  autoscaler_max_workers: 4,
  autoscaler_poll_seconds: 30,
  active_workers: [],
  current_worker_count: 0,
  queue_depth: 0,
  recommended_worker_count: 1,
  last_scale_action: null,
  last_scale_at: null,
  last_error: null,
};

export default function AdminWorkerScalingPage() {
  const [settings, setSettings] = useState<AutoscalerSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadSettings() {
    const response = await authFetch("/api/v1/admin/settings/autoscaler", { cache: "no-store" });
    if (!response.ok) {
      setError("Failed to load autoscaler settings.");
      setLoading(false);
      return;
    }
    const payload = await response.json();
    setSettings(payload.data);
    setLoading(false);
  }

  useEffect(() => {
    loadSettings();
    const intervalId = window.setInterval(() => {
      loadSettings();
    }, 10000);
    return () => window.clearInterval(intervalId);
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    setError(null);
    const response = await authFetch("/api/v1/admin/settings/autoscaler", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        autoscaler_enabled: settings.autoscaler_enabled,
        autoscaler_jobs_per_worker: Math.max(settings.autoscaler_jobs_per_worker, 1),
        autoscaler_min_workers: Math.max(settings.autoscaler_min_workers, 1),
        autoscaler_max_workers: Math.max(settings.autoscaler_max_workers, 1),
        autoscaler_poll_seconds: Math.max(settings.autoscaler_poll_seconds, 5),
      }),
    });
    setSaving(false);
    if (!response.ok) {
      setError("Failed to save autoscaler settings.");
      return;
    }
    const payload = await response.json();
    setSettings(payload.data);
    setMessage("Worker scaling settings saved.");
  }

  return (
    <AdminShell
      title="Worker Scaling"
      description="Observe autoscaler state and control automatic worker scaling based on queue pressure."
    >
      <section className="panel">
        <h2>Autoscaler</h2>
        {loading ? (
          <div className="empty-state">
            <strong>Loading autoscaler state.</strong>
            <p>Fetching worker scaling status from the backend.</p>
          </div>
        ) : (
          <form className="stack-form" onSubmit={handleSubmit}>
            <label className="toggle-row">
              <div>
                <strong>Enable autoscaling</strong>
                <small>Turn the autoscaler loop on or off.</small>
              </div>
              <input
                checked={settings.autoscaler_enabled}
                onChange={(event) => setSettings((current) => ({ ...current, autoscaler_enabled: event.target.checked }))}
                type="checkbox"
              />
            </label>
            <label>
              Max queued jobs per worker
              <input
                min={1}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, autoscaler_jobs_per_worker: Math.max(Number.parseInt(event.target.value || "1", 10) || 1, 1) }))
                }
                type="number"
                value={settings.autoscaler_jobs_per_worker}
              />
            </label>
            <label>
              Minimum workers
              <input
                min={1}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, autoscaler_min_workers: Math.max(Number.parseInt(event.target.value || "1", 10) || 1, 1) }))
                }
                type="number"
                value={settings.autoscaler_min_workers}
              />
            </label>
            <label>
              Maximum workers
              <input
                min={1}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, autoscaler_max_workers: Math.max(Number.parseInt(event.target.value || "1", 10) || 1, 1) }))
                }
                type="number"
                value={settings.autoscaler_max_workers}
              />
            </label>
            <label>
              Poll interval seconds
              <input
                min={5}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, autoscaler_poll_seconds: Math.max(Number.parseInt(event.target.value || "5", 10) || 5, 5) }))
                }
                type="number"
                value={settings.autoscaler_poll_seconds}
              />
            </label>
            <button className="primary-button" disabled={saving} type="submit">
              {saving ? "Saving..." : "Save scaling settings"}
            </button>
            {message ? <p className="form-success">{message}</p> : null}
            {error ? <p className="form-error">{error}</p> : null}
          </form>
        )}
      </section>

      <section className="panel">
        <h2>Runtime Status</h2>
        <div className="table-wrap">
          <table className="simple-table">
            <tbody>
              <tr><th>Current workers</th><td>{settings.current_worker_count}</td></tr>
              <tr><th>Recommended workers</th><td>{settings.recommended_worker_count}</td></tr>
              <tr><th>Queue depth</th><td>{settings.queue_depth}</td></tr>
              <tr><th>Last action</th><td>{settings.last_scale_action ?? "none"}</td></tr>
              <tr><th>Last scale time</th><td>{settings.last_scale_at ?? "never"}</td></tr>
              <tr><th>Last error</th><td>{settings.last_error ?? "none"}</td></tr>
            </tbody>
          </table>
        </div>
        <div className="inline-form-note">
          <strong>Active workers:</strong> {settings.active_workers.length ? settings.active_workers.join(", ") : "none"}
        </div>
      </section>
    </AdminShell>
  );
}
