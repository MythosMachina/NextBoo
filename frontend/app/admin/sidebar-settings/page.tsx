"use client";

import { FormEvent, useEffect, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type SidebarSettings = {
  sidebar_general_limit: number;
  sidebar_meta_limit: number;
  sidebar_character_limit: number;
  sidebar_artist_limit: number;
  sidebar_series_limit: number;
  sidebar_creature_limit: number;
};

const DEFAULT_SETTINGS: SidebarSettings = {
  sidebar_general_limit: 30,
  sidebar_meta_limit: 10,
  sidebar_character_limit: 15,
  sidebar_artist_limit: 15,
  sidebar_series_limit: 15,
  sidebar_creature_limit: 15,
};

export default function AdminSidebarSettingsPage() {
  const [formState, setFormState] = useState<SidebarSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadSettings() {
      const response = await authFetch("/api/v1/admin/settings/sidebar");
      if (!response.ok) {
        setError("Failed to load sidebar settings.");
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

    const response = await authFetch("/api/v1/admin/settings/sidebar", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        Object.fromEntries(
          Object.entries(formState).map(([key, value]) => [key, Number.isFinite(value) ? Math.max(value, 0) : 0])
        )
      )
    });

    setSaving(false);
    if (!response.ok) {
      setError("Failed to save sidebar settings.");
      return;
    }
    const payload = await response.json();
    setFormState(payload.data);
    setMessage("Sidebar settings saved.");
  }

  return (
    <AdminShell
      title="Sidebar Settings"
      description="Configure how many tags are shown per sidebar category without relying on a single global top-tag pool."
    >
      <section className="panel">
        <h2>Sidebar Limits</h2>
        {loading ? (
          <div className="empty-state">
            <strong>Loading settings.</strong>
            <p>Fetching current sidebar limits from the database.</p>
          </div>
        ) : (
          <form className="stack-form" onSubmit={handleSubmit}>
            <label>
              General tags
              <input
                min={0}
                onChange={(event) => setFormState((current) => ({ ...current, sidebar_general_limit: Number.parseInt(event.target.value || "0", 10) }))}
                type="number"
                value={formState.sidebar_general_limit}
              />
            </label>
            <label>
              Promoted meta tags
              <input
                min={0}
                onChange={(event) => setFormState((current) => ({ ...current, sidebar_meta_limit: Number.parseInt(event.target.value || "0", 10) }))}
                type="number"
                value={formState.sidebar_meta_limit}
              />
            </label>
            <label>
              Character tags
              <input
                min={0}
                onChange={(event) => setFormState((current) => ({ ...current, sidebar_character_limit: Number.parseInt(event.target.value || "0", 10) }))}
                type="number"
                value={formState.sidebar_character_limit}
              />
            </label>
            <label>
              Artist tags
              <input
                min={0}
                onChange={(event) => setFormState((current) => ({ ...current, sidebar_artist_limit: Number.parseInt(event.target.value || "0", 10) }))}
                type="number"
                value={formState.sidebar_artist_limit}
              />
            </label>
            <label>
              Series tags
              <input
                min={0}
                onChange={(event) => setFormState((current) => ({ ...current, sidebar_series_limit: Number.parseInt(event.target.value || "0", 10) }))}
                type="number"
                value={formState.sidebar_series_limit}
              />
            </label>
            <label>
              Creature tags
              <input
                min={0}
                onChange={(event) => setFormState((current) => ({ ...current, sidebar_creature_limit: Number.parseInt(event.target.value || "0", 10) }))}
                type="number"
                value={formState.sidebar_creature_limit}
              />
            </label>
            <button className="primary-button" disabled={saving} type="submit">
              {saving ? "Saving..." : "Save settings"}
            </button>
            {message ? <p className="form-success">{message}</p> : null}
            {error ? <p className="form-error">{error}</p> : null}
          </form>
        )}
      </section>
    </AdminShell>
  );
}
