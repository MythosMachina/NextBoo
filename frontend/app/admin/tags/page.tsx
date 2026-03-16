"use client";

import { FormEvent, useEffect, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type TagItem = {
  id: number;
  name_normalized: string;
  display_name: string;
  category: "general" | "character" | "copyright" | "meta" | "artist";
  is_active: boolean;
  is_locked: boolean;
  alias_count: number;
  image_count: number;
  is_name_pattern: boolean;
};

export default function AdminTagsPage() {
  const [query, setQuery] = useState("");
  const [tags, setTags] = useState<TagItem[]>([]);
  const [aliasName, setAliasName] = useState("");
  const [aliasTarget, setAliasTarget] = useState("");
  const [mergeSource, setMergeSource] = useState("");
  const [mergeTarget, setMergeTarget] = useState("");
  const [mergeReason, setMergeReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadTags(nextQuery = query) {
    const response = await authFetch(`/api/v1/tags/admin/list?q=${encodeURIComponent(nextQuery)}`, { cache: "no-store" });
    if (!response.ok) {
      setError("Failed to load tags.");
      return;
    }
    const payload = await response.json();
    setTags(payload.data);
  }

  useEffect(() => {
    loadTags("");
  }, []);

  async function updateTag(tag: TagItem, patch: Partial<TagItem>) {
    setBusy(true);
    setError(null);
    const response = await authFetch(`/api/v1/tags/admin/${tag.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        display_name: patch.display_name ?? tag.display_name,
        category: patch.category ?? tag.category,
        is_active: patch.is_active ?? tag.is_active,
        is_locked: patch.is_locked ?? tag.is_locked,
      }),
    });
    setBusy(false);
    if (!response.ok) {
      setError("Failed to update tag.");
      return;
    }
    setMessage(`Updated ${tag.name_normalized}.`);
    await loadTags();
  }

  async function submitAlias(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const response = await authFetch("/api/v1/tags/admin/alias", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ alias_name: aliasName, target_tag_name: aliasTarget, alias_type: "synonym" }),
    });
    setBusy(false);
    if (!response.ok) {
      setError("Failed to save alias.");
      return;
    }
    setAliasName("");
    setAliasTarget("");
    setMessage("Alias saved.");
    await loadTags();
  }

  async function submitMerge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const response = await authFetch("/api/v1/tags/admin/merge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_tag_name: mergeSource, target_tag_name: mergeTarget, reason: mergeReason || null }),
    });
    setBusy(false);
    if (!response.ok) {
      setError("Failed to merge tags.");
      return;
    }
    setMergeSource("");
    setMergeTarget("");
    setMergeReason("");
    setMessage("Tags merged.");
    await loadTags();
  }

  return (
    <AdminShell title="Tags" description="Maintain tags globally with search, lock state, aliases and merges.">
      {message ? <p className="form-success">{message}</p> : null}
      {error ? <p className="form-error">{error}</p> : null}

      <section className="panel">
        <h2>Search tags</h2>
        <div className="row-actions">
          <input className="stack-input" onChange={(event) => setQuery(event.target.value)} placeholder="tag search" value={query} />
          <button className="primary-button" disabled={busy} onClick={() => loadTags(query)} type="button">Search</button>
        </div>
      </section>

      <section className="panel">
        <h2>Alias</h2>
        <form className="stack-form" onSubmit={submitAlias}>
          <div className="admin-form-grid">
            <label>
              Alias
              <input className="stack-input" onChange={(event) => setAliasName(event.target.value)} required value={aliasName} />
            </label>
            <label>
              Target tag
              <input className="stack-input" onChange={(event) => setAliasTarget(event.target.value)} required value={aliasTarget} />
            </label>
          </div>
          <button className="primary-button" disabled={busy} type="submit">Save alias</button>
        </form>
      </section>

      <section className="panel">
        <h2>Merge</h2>
        <form className="stack-form" onSubmit={submitMerge}>
          <div className="admin-form-grid">
            <label>
              Source tag
              <input className="stack-input" onChange={(event) => setMergeSource(event.target.value)} required value={mergeSource} />
            </label>
            <label>
              Target tag
              <input className="stack-input" onChange={(event) => setMergeTarget(event.target.value)} required value={mergeTarget} />
            </label>
            <label>
              Reason
              <input className="stack-input" onChange={(event) => setMergeReason(event.target.value)} value={mergeReason} />
            </label>
          </div>
          <button className="danger-button" disabled={busy} type="submit">Merge tags</button>
        </form>
      </section>

      <section className="panel">
        <h2>Tag list</h2>
        <div className="table-wrap">
          <table className="simple-table">
            <thead>
              <tr>
                <th>Tag</th>
                <th>Category</th>
                <th>Images</th>
                <th>Aliases</th>
                <th>State</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {tags.map((tag) => (
                <tr key={tag.id}>
                  <td>
                    <div className="table-primary-cell">{tag.display_name}</div>
                    <div className="table-secondary-cell">{tag.name_normalized}</div>
                    {tag.is_name_pattern ? <div className="table-secondary-cell">Danbooru-style name pattern</div> : null}
                  </td>
                  <td>{tag.category}</td>
                  <td>{tag.image_count}</td>
                  <td>{tag.alias_count}</td>
                  <td>{tag.is_active ? (tag.is_locked ? "active / locked" : "active") : "inactive"}</td>
                  <td>
                    <div className="row-actions">
                      <button className="theme-toggle" disabled={busy} onClick={() => updateTag(tag, { is_locked: !tag.is_locked })} type="button">
                        {tag.is_locked ? "Unlock" : "Lock"}
                      </button>
                      <button className="theme-toggle" disabled={busy} onClick={() => updateTag(tag, { is_active: !tag.is_active })} type="button">
                        {tag.is_active ? "Disable" : "Enable"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!tags.length ? (
                <tr><td colSpan={6}>No tags found.</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </AdminShell>
  );
}
