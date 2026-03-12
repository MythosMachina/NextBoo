"use client";

import { authFetch } from "../../../components/auth";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { AdminShell } from "../../../components/admin-shell";
import { ModerationImageActions } from "../../../components/moderation-image-actions";
import { TagLink } from "../../../components/tag-link";

type Variant = {
  variant_type: "original" | "thumb";
  url: string | null;
};

type TagItem = {
  tag: {
    id: number;
    name_normalized: string;
    display_name: string;
    category: "general" | "character" | "copyright" | "meta" | "artist";
  };
  source: "auto" | "user" | "system";
};

type ImageDetail = {
  id: string;
  uuid_short: string;
  original_filename: string;
  width: number;
  height: number;
  rating: "general" | "sensitive" | "questionable" | "explicit";
  visibility_status: "visible" | "hidden" | "deleted";
  uploaded_by: { id: number; username: string } | null;
  variants: Variant[];
  tags: TagItem[];
  manual_tag_names: string[];
};

type ReportItem = {
  id: number;
  reason: string;
  message: string | null;
  status: string;
  reported_by_username: string | null;
  created_at: string;
};

export default function AdminContentDetailPage() {
  const params = useParams<{ id: string }>();
  const [image, setImage] = useState<ImageDetail | null>(null);
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function loadAll() {
    setError(null);
    const [imageResponse, reportsResponse] = await Promise.all([
      authFetch(`/api/v1/images/${params.id}`, { cache: "no-store" }),
      authFetch(`/api/v1/moderation/reports?image_id=${encodeURIComponent(params.id)}`, { cache: "no-store" })
    ]);

    if (!imageResponse.ok) {
      setError("Failed to load moderation target.");
      return;
    }
    const imagePayload = await imageResponse.json();
    setImage(imagePayload.data);

    if (reportsResponse.ok) {
      const reportsPayload = await reportsResponse.json();
      setReports(reportsPayload.data);
    }
  }

  useEffect(() => {
    loadAll();
  }, [params.id]);

  const original = image?.variants.find((variant) => variant.variant_type === "original");

  return (
    <AdminShell title="Moderation Detail" description="Single-post moderation workspace for image review and action.">
      {error ? <p className="form-error">{error}</p> : null}
      {image ? (
        <div className="post-detail-layout">
          <section className="post-view panel">
            <h2>Post</h2>
            <div className="post-view-inner">
              {original?.url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img alt={image.original_filename} className="post-full-image" src={original.url} />
              ) : null}
            </div>
          </section>

          <aside className="post-sidebar">
            <section className="panel">
              <h2>Details</h2>
              <ul className="link-list">
                <li>ID: {image.id}</li>
                <li>Short: {image.uuid_short}</li>
                <li>Size: {image.width}x{image.height}</li>
                <li>Rating: {image.rating}</li>
                <li>Visibility: {image.visibility_status}</li>
                <li>Uploader: {image.uploaded_by?.username ?? "unknown"}</li>
              </ul>
            </section>

            <section className="panel">
              <h2>Reports</h2>
              <div className="moderation-report-list">
                {reports.length ? (
                  reports.map((report) => (
                    <div className="moderation-report-item" key={report.id}>
                      <strong>{report.reason}</strong>
                      <span>{report.status}</span>
                      <p>{report.message ?? "No note provided."}</p>
                      <small>{report.reported_by_username ?? "unknown"}</small>
                    </div>
                  ))
                ) : (
                  <div className="empty-state compact-empty">
                    <strong>No reports</strong>
                    <p>This post is currently not associated with any report record.</p>
                  </div>
                )}
              </div>
            </section>

            <section className="panel">
              <h2>Tags</h2>
              <div className="tag-sections">
                <div className="tag-list">
                  {image.tags.map((item) => (
                    <TagLink
                      className={`tag tag-${item.tag.category}`}
                      href={`/?q=${encodeURIComponent(item.tag.name_normalized)}`}
                      key={`${item.tag.id}-${item.source}`}
                      tagName={item.tag.name_normalized}
                    >
                      {item.tag.display_name}
                    </TagLink>
                  ))}
                </div>
              </div>
            </section>

            <ModerationImageActions
              imageId={image.id}
              onUpdated={loadAll}
              rating={image.rating}
              tagNames={image.tags.map((item) => item.tag.name_normalized)}
              visibilityStatus={image.visibility_status}
            />
          </aside>
        </div>
      ) : (
        <div className="empty-state">
          <strong>Loading moderation target.</strong>
          <p>Fetching post, reports and moderation metadata.</p>
        </div>
      )}
    </AdminShell>
  );
}
