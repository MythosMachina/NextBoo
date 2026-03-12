"use client";

import { useEffect, useMemo, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type ModerationImage = {
  id: string;
  uuid_short: string;
  original_filename: string;
  rating: "general" | "sensitive" | "questionable" | "explicit";
  visibility_status: "visible" | "hidden" | "deleted";
  uploaded_by_username: string | null;
  report_count_open: number;
  created_at: string;
};

export default function AdminContentPage() {
  const [images, setImages] = useState<ModerationImage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [savingImageId, setSavingImageId] = useState<string | null>(null);

  async function loadImages() {
    const response = await authFetch("/api/v1/moderation/images");
    if (!response.ok) {
      setError("Failed to load moderation content.");
      return;
    }
    const payload = await response.json();
    setImages(payload.data);
  }

  useEffect(() => {
    loadImages();
  }, []);

  async function setVisibility(imageId: string, visibilityStatus: ModerationImage["visibility_status"]) {
    setSavingImageId(imageId);
    setError(null);
    const response = await authFetch(`/api/v1/images/${imageId}/visibility`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        visibility_status: visibilityStatus,
        reason: "moderation_panel"
      })
    });
    setSavingImageId(null);
    if (!response.ok) {
      setError("Failed to update visibility.");
      return;
    }
    await loadImages();
  }

  return (
    <AdminShell title="Content" description="Hide, restore or delete posts that require moderation action.">
      {error ? <p className="form-error">{error}</p> : null}
      <section className="panel">
        <h2>Moderation Queue</h2>
        <div className="table-wrap">
          <table className="simple-table">
            <thead>
              <tr>
                <th>Post</th>
                <th>Rating</th>
                <th>Visibility</th>
                <th>Uploader</th>
                <th>Open Reports</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {images.map((image) => (
                <tr key={image.id}>
                  <td><a href={`/admin/content/${image.id}`}>#{image.uuid_short}</a></td>
                  <td>{image.rating}</td>
                  <td>{image.visibility_status}</td>
                  <td>{image.uploaded_by_username ?? "unknown"}</td>
                  <td>{image.report_count_open}</td>
                  <td>
                    <div className="row-actions">
                      {image.visibility_status !== "visible" ? (
                        <button
                          className="theme-toggle"
                          disabled={savingImageId === image.id}
                          onClick={() => setVisibility(image.id, "visible")}
                          type="button"
                        >Restore</button>
                      ) : null}
                      {image.visibility_status !== "hidden" ? (
                        <button
                          className="theme-toggle"
                          disabled={savingImageId === image.id}
                          onClick={() => setVisibility(image.id, "hidden")}
                          type="button"
                        >Hide</button>
                      ) : null}
                      <a className="admin-inline-link" href={`/admin/content/${image.id}`}>Open</a>
                    </div>
                  </td>
                </tr>
              ))}
              {!images.length ? (
                <tr>
                  <td colSpan={6}>No items currently require moderation.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </AdminShell>
  );
}
