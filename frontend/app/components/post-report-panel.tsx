"use client";

import { FormEvent, useState } from "react";
import { authFetch, useAuthState } from "./auth";

export function PostReportPanel({ imageId }: { imageId: string }) {
  const { authenticated } = useAuthState();
  const [open, setOpen] = useState(false);
  const [reportReason, setReportReason] = useState("bad_tags");
  const [reportMessage, setReportMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setErrorMessage(null);
    setStatusMessage(null);
    const response = await authFetch(`/api/v1/images/${imageId}/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reason: reportReason,
        message: reportMessage || null
      })
    });
    setSaving(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setErrorMessage(payload?.detail ?? "Report failed.");
      return;
    }
    setReportMessage("");
    setStatusMessage("Report submitted. The post was moved to moderation review.");
    setOpen(false);
  }

  if (!authenticated) {
    return null;
  }

  return (
    <>
      <button className="theme-toggle" onClick={() => setOpen(true)} type="button">
        Report Post
      </button>
      {statusMessage ? <span className="form-success">{statusMessage}</span> : null}

      {open ? (
        <div className="modal-backdrop" onClick={() => setOpen(false)}>
          <div className="modal-panel" onClick={(event) => event.stopPropagation()}>
            <h2>Report Post</h2>
            <form className="stack-form" onSubmit={handleReport}>
              <label>
                Reason
                <select className="stack-select" onChange={(event) => setReportReason(event.target.value)} value={reportReason}>
                  <option value="bad_tags">Bad tags</option>
                  <option value="wrong_rating">Wrong rating</option>
                  <option value="duplicate">Duplicate</option>
                  <option value="illegal_content">Illegal content</option>
                  <option value="other">Other</option>
                </select>
              </label>
              <label>
                Note
                <textarea
                  className="stack-textarea"
                  onChange={(event) => setReportMessage(event.target.value)}
                  rows={4}
                  value={reportMessage}
                />
              </label>
              {errorMessage ? <p className="form-error">{errorMessage}</p> : null}
              <div className="row-actions">
                <button className="primary-button" disabled={saving} type="submit">
                  {saving ? "Sending..." : "Submit Report"}
                </button>
                <button className="theme-toggle" onClick={() => setOpen(false)} type="button">
                  Close
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </>
  );
}
