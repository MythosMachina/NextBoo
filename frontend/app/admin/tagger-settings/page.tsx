"use client";

import { useEffect, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type TaggerSettings = {
  provider: string;
  retag_all_running: boolean;
  retag_all_pending: boolean;
};

const DEFAULT_SETTINGS: TaggerSettings = {
  provider: "camie",
  retag_all_running: false,
  retag_all_pending: false,
};

export default function AdminTaggerSettingsPage() {
  const [settings, setSettings] = useState<TaggerSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [queueingRetag, setQueueingRetag] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadSettings() {
      const response = await authFetch("/api/v1/admin/settings/tagger");
      if (!response.ok) {
        setError("Failed to load tagger settings.");
        setLoading(false);
        return;
      }
      const payload = await response.json();
      setSettings(payload.data);
      setLoading(false);
    }

    loadSettings();
  }, []);

  async function reloadSettings() {
    const response = await authFetch("/api/v1/admin/settings/tagger");
    if (!response.ok) {
      setError("Failed to refresh tagger settings.");
      return;
    }
    const payload = await response.json();
    setSettings(payload.data);
  }

  async function handlePruneAndRetag() {
    if (
      !window.confirm(
        "Prune all current auto tags and re-run the full image library through the active tagger? This can take a while."
      )
    ) {
      return;
    }

    setQueueingRetag(true);
    setMessage(null);
    setError(null);

    const response = await authFetch("/api/v1/admin/settings/tagger/prune-retag", {
      method: "POST",
    });

    setQueueingRetag(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? "Failed to queue prune-and-retag.");
      await reloadSettings();
      return;
    }

    const payload = await response.json();
    setSettings(payload.data);
    setMessage("Prune-and-retag queued for Camie Tagger.");
  }

  return (
    <AdminShell
      title="Tagger Maintenance"
      description="Camie Tagger is now the default ingest provider. Use this page to monitor and trigger full-library retag maintenance."
    >
      <section className="panel">
        <h2>Camie Tagger</h2>
        {loading ? (
          <div className="empty-state">
            <strong>Loading tagger settings.</strong>
            <p>Fetching the active tagger provider from the database.</p>
          </div>
        ) : (
          <div className="stack-form">
            <div className="inline-form-note">
              <strong>Active provider:</strong> Camie Tagger
            </div>
            <div className="inline-form-note">
              <strong>Retag status:</strong>{" "}
              {settings.retag_all_running
                ? "Running"
                : settings.retag_all_pending
                  ? "Queued"
                  : "Idle"}
            </div>
            <button
              className="danger-button"
              disabled={queueingRetag || settings.retag_all_running || settings.retag_all_pending}
              onClick={handlePruneAndRetag}
              type="button"
            >
              {queueingRetag
                ? "Queueing..."
                : settings.retag_all_running
                  ? "Retag running"
                  : settings.retag_all_pending
                    ? "Retag queued"
                    : "Prune All Tags and Retag"}
            </button>
            {message ? <p className="form-success">{message}</p> : null}
            {error ? <p className="form-error">{error}</p> : null}
          </div>
        )}
      </section>
    </AdminShell>
  );
}
