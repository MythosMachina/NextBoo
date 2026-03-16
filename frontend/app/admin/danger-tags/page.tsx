"use client";

import { FormEvent, useEffect, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type DangerTag = {
  id: number;
  tag_id: number;
  tag_name: string;
  display_name: string;
  reason: string | null;
  is_enabled: boolean;
  created_at: string;
};

export default function AdminDangerTagsPage() {
  const [items, setItems] = useState<DangerTag[]>([]);
  const [tagName, setTagName] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadDangerTags() {
    const response = await authFetch("/api/v1/tags/admin/danger-tags", { cache: "no-store" });
    if (!response.ok) {
      setError("Failed to load danger tags.");
      return;
    }
    const payload = await response.json();
    setItems(payload.data);
  }

  useEffect(() => {
    loadDangerTags();
  }, []);

  async function saveDangerTag(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const response = await authFetch("/api/v1/tags/admin/danger-tags", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tag_name: tagName, reason: reason || null, is_enabled: true }),
    });
    setBusy(false);
    if (!response.ok) {
      setError("Failed to save danger tag.");
      return;
    }
    setTagName("");
    setReason("");
    setMessage("Danger tag saved.");
    await loadDangerTags();
  }

  async function removeDangerTag(id: number) {
    setBusy(true);
    setError(null);
    const response = await authFetch(`/api/v1/tags/admin/danger-tags/${id}`, { method: "DELETE" });
    setBusy(false);
    if (!response.ok) {
      setError("Failed to delete danger tag.");
      return;
    }
    setMessage("Danger tag deleted.");
    await loadDangerTags();
  }

  return (
    <AdminShell title="Danger Tags" description="Automatically hold uploads for moderation when these tags appear after tagging.">
      {message ? <p className="form-success">{message}</p> : null}
      {error ? <p className="form-error">{error}</p> : null}

      <section className="panel">
        <h2>Add danger tag</h2>
        <form className="stack-form" onSubmit={saveDangerTag}>
          <div className="admin-form-grid">
            <label>
              Tag
              <input className="stack-input" onChange={(event) => setTagName(event.target.value)} required value={tagName} />
            </label>
            <label>
              Reason
              <input className="stack-input" onChange={(event) => setReason(event.target.value)} value={reason} />
            </label>
          </div>
          <button className="danger-button" disabled={busy} type="submit">Save danger tag</button>
        </form>
      </section>

      <section className="panel">
        <h2>Configured danger tags</h2>
        <div className="table-wrap">
          <table className="simple-table">
            <thead>
              <tr>
                <th>Tag</th>
                <th>Reason</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{item.display_name}</td>
                  <td>{item.reason ?? "-"}</td>
                  <td>
                    <button className="danger-button compact-danger" disabled={busy} onClick={() => removeDangerTag(item.id)} type="button">
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {!items.length ? <tr><td colSpan={3}>No danger tags configured.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </section>
    </AdminShell>
  );
}
