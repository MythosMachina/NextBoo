"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AccountShell } from "../../../components/account-shell";
import { authFetch, useAuthState } from "../../../components/auth";

type Variant = {
  variant_type: "original" | "thumb";
  url: string | null;
};

type ImageDetail = {
  id: string;
  uuid_short: string;
  original_filename: string;
  rating: "general" | "sensitive" | "questionable" | "explicit";
  visibility_status: "visible" | "hidden" | "deleted";
  uploaded_by: { id: number; username: string } | null;
  manual_tag_names: string[];
  variants: Variant[];
};

export default function AccountUploadDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuthState();
  const [image, setImage] = useState<ImageDetail | null>(null);
  const [manualTags, setManualTags] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadImage() {
    const response = await authFetch(`/api/v1/images/${params.id}`, { cache: "no-store" });
    if (!response.ok) {
      setError("Failed to load your upload.");
      return;
    }
    const payload = await response.json();
    setImage(payload.data);
    setManualTags(payload.data.manual_tag_names.join(" "));
  }

  useEffect(() => {
    loadImage();
  }, [params.id]);

  async function saveTags() {
    setSaving(true);
    setError(null);
    const response = await authFetch(`/api/v1/images/${params.id}/metadata`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        tag_names: manualTags.split(/\s+/).map((item) => item.trim()).filter(Boolean)
      })
    });
    setSaving(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? "Failed to save tags.");
      return;
    }
    setMessage("Tags updated.");
    await loadImage();
  }

  async function deleteUpload() {
    setSaving(true);
    setError(null);
    const response = await authFetch(`/api/v1/images/${params.id}/delete`, { method: "POST" });
    setSaving(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? "Failed to delete post.");
      return;
    }
    router.push("/account/uploads");
  }

  const original = image?.variants.find((variant) => variant.variant_type === "original");
  const isOwner = Boolean(user && image?.uploaded_by?.id && user.id === image.uploaded_by.id);

  return (
    <AccountShell title="Manage Upload" description="Edit your own post tags or remove the post from the system.">
      <div className="post-detail-layout">
        <section className="post-view panel">
          <h2>My Upload</h2>
          <div className="post-view-inner">
            {original?.url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img alt={image?.original_filename ?? "upload"} className="post-full-image" src={original.url} />
            ) : null}
          </div>
        </section>
        <aside className="post-sidebar">
          <section className="panel">
            <h2>Manage Upload</h2>
            {!isOwner ? (
              <div className="empty-state compact-empty">
                <strong>Ownership required.</strong>
                <p>You can only manage your own uploads here.</p>
              </div>
            ) : (
              <div className="stack-form">
                <label>
                  Manual tags
                  <textarea className="stack-textarea" onChange={(event) => setManualTags(event.target.value)} rows={5} value={manualTags} />
                </label>
                <button className="primary-button" disabled={saving} onClick={saveTags} type="button">
                  Save tags
                </button>
                <button className="danger-button" disabled={saving} onClick={deleteUpload} type="button">
                  Delete post
                </button>
                {message ? <p className="form-success">{message}</p> : null}
                {error ? <p className="form-error">{error}</p> : null}
              </div>
            )}
          </section>
        </aside>
      </div>
    </AccountShell>
  );
}
