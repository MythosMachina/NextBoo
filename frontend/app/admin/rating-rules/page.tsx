"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type RatingRule = {
  id: number;
  tag_id: number;
  tag_name: string;
  display_name: string;
  tag_category: "general" | "character" | "copyright" | "meta" | "artist";
  target_rating: "general" | "sensitive" | "questionable" | "explicit";
  boost: number;
  is_enabled: boolean;
};

export default function AdminRatingRulesPage() {
  const [rules, setRules] = useState<RatingRule[]>([]);
  const [tagName, setTagName] = useState("");
  const [targetRating, setTargetRating] = useState<RatingRule["target_rating"]>("questionable");
  const [boost, setBoost] = useState("0.24");
  const [isEnabled, setIsEnabled] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadRules() {
    const response = await authFetch("/api/v1/moderation/rating-rules", { cache: "no-store" });
    if (!response.ok) {
      setError("Failed to load rating rules.");
      return;
    }
    const payload = await response.json();
    setRules(payload.data);
  }

  useEffect(() => {
    loadRules();
  }, []);

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    setError(null);
    const response = await authFetch("/api/v1/moderation/rating-rules", {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        tag_name: tagName,
        target_rating: targetRating,
        boost: Number.parseFloat(boost),
        is_enabled: isEnabled
      })
    });
    setBusy(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? "Failed to save rating rule.");
      return;
    }
    setTagName("");
    setBoost(
      targetRating === "explicit"
        ? "0.34"
        : targetRating === "questionable"
          ? "0.24"
          : targetRating === "sensitive"
            ? "0.20"
            : "0.18"
    );
    setMessage("Rating rule saved.");
    await loadRules();
  }

  async function handleDelete(ruleId: number) {
    if (!window.confirm("Delete this rating rule?")) {
      return;
    }
    setBusy(true);
    setMessage(null);
    setError(null);
    const response = await authFetch(`/api/v1/moderation/rating-rules/${ruleId}`, { method: "DELETE" });
    setBusy(false);
    if (!response.ok) {
      setError("Failed to delete rating rule.");
      return;
    }
    setMessage("Rating rule deleted.");
    await loadRules();
  }

  async function handleReclassify() {
    if (!window.confirm("Apply current rating rules to existing images?")) {
      return;
    }
    setBusy(true);
    setMessage(null);
    setError(null);
    const response = await authFetch("/api/v1/moderation/rating-rules/reclassify", { method: "POST" });
    setBusy(false);
    if (!response.ok) {
      setError("Failed to reclassify existing images.");
      return;
    }
    const payload = await response.json();
    setMessage(`Reclassified ${payload.data.changed_images} images.`);
  }

  return (
    <AdminShell
      title="Rating Rules"
      description="Bias automated ratings by promoted tag buckets. Sensitive, questionable and explicit rules can elevate ratings; general rules strengthen the least restrictive bucket."
    >
      {message ? <p className="form-success">{message}</p> : null}
      {error ? <p className="form-error">{error}</p> : null}

      <section className="panel">
        <h2>Create or update rule</h2>
        <form className="stack-form" onSubmit={handleSave}>
          <div className="admin-form-grid">
            <label>
              Tag
              <input
                className="stack-input"
                onChange={(event) => setTagName(event.target.value)}
                placeholder="tag_name"
                required
                type="text"
                value={tagName}
              />
            </label>
            <label>
              Target rating
              <select
                className="stack-select"
                onChange={(event) => setTargetRating(event.target.value as RatingRule["target_rating"])}
                value={targetRating}
              >
                <option value="general">general</option>
                <option value="sensitive">sensitive</option>
                <option value="questionable">questionable</option>
                <option value="explicit">explicit</option>
              </select>
            </label>
            <label>
              Boost
              <input
                className="stack-input"
                max="1"
                min="0"
                onChange={(event) => setBoost(event.target.value)}
                required
                step="0.01"
                type="number"
                value={boost}
              />
            </label>
            <label className="checkbox-row">
              <input checked={isEnabled} onChange={(event) => setIsEnabled(event.target.checked)} type="checkbox" />
              Enabled
            </label>
          </div>
          <div className="row-actions">
            <button className="primary-button" disabled={busy} type="submit">
              Save rule
            </button>
            <button className="theme-toggle" disabled={busy} onClick={handleReclassify} type="button">
              Reclassify existing
            </button>
          </div>
        </form>
      </section>

      <section className="panel">
        <h2>Current rules</h2>
        <div className="table-wrap">
          <table className="simple-table">
            <thead>
              <tr>
                <th>Tag</th>
                <th>Category</th>
                <th>Target</th>
                <th>Boost</th>
                <th>Enabled</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.id}>
                  <td>{rule.display_name}</td>
                  <td>{rule.tag_category}</td>
                  <td>{rule.target_rating}</td>
                  <td>{rule.boost.toFixed(2)}</td>
                  <td>{rule.is_enabled ? "yes" : "no"}</td>
                  <td>
                    <button className="danger-button" disabled={busy} onClick={() => handleDelete(rule.id)} type="button">
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {!rules.length ? (
                <tr>
                  <td colSpan={6}>No rating rules configured yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </AdminShell>
  );
}
