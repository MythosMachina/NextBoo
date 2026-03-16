"use client";

import { FormEvent, useEffect, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type TermsOfService = {
  title: string;
  version: string;
  paragraphs: string[];
  updated_at: string | null;
};

const DEFAULT_TERMS: TermsOfService = {
  title: "NextBoo Terms of Service",
  version: "",
  paragraphs: [""],
  updated_at: null,
};

export default function AdminTermsOfServicePage() {
  const [formState, setFormState] = useState<TermsOfService>(DEFAULT_TERMS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadTerms() {
      const response = await authFetch("/api/v1/admin/settings/tos", { cache: "no-store" });
      if (!response.ok) {
        setError("Failed to load Terms of Service.");
        setLoading(false);
        return;
      }
      const payload = await response.json();
      setFormState(payload.data);
      setLoading(false);
    }

    loadTerms();
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    setError(null);

    const response = await authFetch("/api/v1/admin/settings/tos", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: formState.title,
        paragraphs: formState.paragraphs.map((paragraph) => paragraph.trim()).filter(Boolean),
      }),
    });

    setSaving(false);
    if (!response.ok) {
      setError("Failed to save Terms of Service.");
      return;
    }

    const payload = await response.json();
    setFormState(payload.data);
    setMessage("Terms of Service saved.");
  }

  function updateParagraph(index: number, value: string) {
    setFormState((current) => ({
      ...current,
      paragraphs: current.paragraphs.map((paragraph, paragraphIndex) => (paragraphIndex === index ? value : paragraph)),
    }));
  }

  function removeParagraph(index: number) {
    setFormState((current) => {
      const nextParagraphs = current.paragraphs.filter((_, paragraphIndex) => paragraphIndex !== index);
      return {
        ...current,
        paragraphs: nextParagraphs.length ? nextParagraphs : [""],
      };
    });
  }

  function addParagraph() {
    setFormState((current) => ({
      ...current,
      paragraphs: [...current.paragraphs, ""],
    }));
  }

  return (
    <AdminShell
      title="Terms of Service"
      description="Edit the published Terms of Service shown during invite redemption. New registrations must accept the current version."
    >
      <section className="panel">
        <h2>ToS Editor</h2>
        {loading ? (
          <div className="empty-state">
            <strong>Loading terms.</strong>
            <p>Fetching the current published version.</p>
          </div>
        ) : (
          <form className="stack-form tos-editor-form" onSubmit={handleSubmit}>
            <label>
              Title
              <input
                onChange={(event) => setFormState((current) => ({ ...current, title: event.target.value }))}
                type="text"
                value={formState.title}
              />
            </label>
            <div className="tos-editor-toolbar">
              <div className="tos-editor-meta">
                <span>Version {formState.version || "pending"}</span>
                {formState.updated_at ? <span>Updated {new Date(formState.updated_at).toLocaleString()}</span> : null}
              </div>
              <button className="secondary-button" onClick={addParagraph} type="button">
                Add paragraph
              </button>
            </div>
            <div className="tos-editor-blocks">
              {formState.paragraphs.map((paragraph, index) => (
                <article className="tos-editor-block" key={`paragraph-${index}`}>
                  <div className="tos-editor-block-head">
                    <strong>Paragraph {index + 1}</strong>
                    <button
                      className="danger-button compact-danger"
                      disabled={formState.paragraphs.length <= 1}
                      onClick={() => removeParagraph(index)}
                      type="button"
                    >
                      Remove
                    </button>
                  </div>
                  <textarea
                    className="stack-textarea"
                    onChange={(event) => updateParagraph(index, event.target.value)}
                    rows={5}
                    value={paragraph}
                  />
                </article>
              ))}
            </div>
            <button className="primary-button" disabled={saving} type="submit">
              {saving ? "Saving..." : "Publish Terms"}
            </button>
            {message ? <p className="form-success">{message}</p> : null}
            {error ? <p className="form-error">{error}</p> : null}
          </form>
        )}
      </section>
    </AdminShell>
  );
}
