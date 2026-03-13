"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { authFetch, useAuthState } from "../../components/auth";
import { PostReportPanel } from "../../components/post-report-panel";
import { TagLink } from "../../components/tag-link";

type Variant = {
  variant_type: "original" | "thumb";
  relative_path: string;
  mime_type: string;
  width: number;
  height: number;
  file_size: number;
  url: string | null;
};

type TagItem = {
  tag: {
    id: number;
    name_normalized: string;
    display_name: string;
    category: "general" | "character" | "copyright" | "meta" | "artist";
  };
  confidence: number | null;
  source: "auto" | "user" | "system";
  is_manual: boolean;
  rating_cue?: "questionable" | "explicit" | null;
};

type ImageDetail = {
  id: string;
  uuid_short: string;
  original_filename: string;
  width: number;
  height: number;
  rating: "general" | "sensitive" | "questionable" | "explicit";
  visibility_status: "visible" | "hidden" | "deleted";
  uploaded_by: {
    id: number;
    username: string;
  } | null;
  variants: Variant[];
  tags: TagItem[];
};

const TAG_CATEGORY_ORDER: TagItem["tag"]["category"][] = [
  "character",
  "artist",
  "copyright",
  "meta",
  "general",
];

const TAG_CATEGORY_LABELS: Record<TagItem["tag"]["category"], string> = {
  character: "Character Tags",
  artist: "Artist Tags",
  copyright: "Series Tags",
  meta: "Meta Tags",
  general: "General Tags",
};

export default function PostDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { isAdmin, isStaff } = useAuthState();
  const [image, setImage] = useState<ImageDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [generalTagsOpen, setGeneralTagsOpen] = useState(false);

  useEffect(() => {
    async function loadImage() {
      setLoading(true);
      setError(null);
      const response = await authFetch(`/api/v1/images/${params.id}`, {
        cache: "no-store",
      });
      if (!response.ok) {
        setLoading(false);
        setError(response.status === 404 ? "Post not found." : "Failed to load post.");
        return;
      }
      const payload = await response.json();
      setImage(payload.data);
      setLoading(false);
    }

    loadImage();
  }, [params.id]);

  if (loading) {
    return (
      <div className="empty-state">
        <strong>Loading post.</strong>
        <p>Fetching image details and moderation state.</p>
      </div>
    );
  }

  if (!image) {
    return (
      <div className="empty-state">
        <strong>Post unavailable.</strong>
        <p>{error ?? "The requested post could not be loaded."}</p>
      </div>
    );
  }

  const original = image.variants.find((variant) => variant.variant_type === "original");
  const originalFileSize = original ? `${(original.file_size / (1024 * 1024)).toFixed(2)} MB` : "unknown";
  const groupedTags = image.tags.reduce<Record<string, TagItem[]>>((acc, item) => {
    const key = item.tag.category;
    acc[key] ??= [];
    acc[key].push(item);
    return acc;
  }, {});
  const orderedTagGroups = TAG_CATEGORY_ORDER
    .map((category) => ({
      category,
      label: TAG_CATEGORY_LABELS[category],
      tags: (groupedTags[category] ?? []).slice().sort((left, right) => left.tag.display_name.localeCompare(right.tag.display_name)),
    }))
    .filter((group) => group.tags.length > 0);

  async function handleDelete() {
    if (!isAdmin || deleting || !image) {
      return;
    }
    const imageId = image.id;
    if (!window.confirm("Really removing this image?")) {
      return;
    }
    setDeleting(true);
    const response = await authFetch(`/api/v1/images/${imageId}/delete`, {
      method: "POST"
    });
    setDeleting(false);
    if (!response.ok) {
      return;
    }
    router.push("/");
  }

  return (
    <div className="post-detail-layout">
      <section className="post-view panel">
        <h2>Post</h2>
        <div className="post-view-inner">
          {original?.url ? (
            original.mime_type.startsWith("video/") ? (
              <video autoPlay className="post-full-image" controls loop playsInline src={original.url} />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img alt={image.original_filename} className="post-full-image" src={original.url} />
            )
          ) : null}
        </div>
        <div className="post-details-block">
          <div className="post-details-header">
            <h3>Details</h3>
            <div className="detail-actions">
              <PostReportPanel imageId={image.id} />
              {isAdmin ? (
                <Link className="theme-toggle" href={`/admin/content/${encodeURIComponent(image.id)}`}>
                  Edit Post
                </Link>
              ) : null}
              {isAdmin ? (
                <button className="danger-button compact-danger" disabled={deleting} onClick={handleDelete} type="button">
                  {deleting ? "Removing..." : "Delete"}
                </button>
              ) : null}
            </div>
          </div>
          <table className="detail-table">
            <tbody>
              <tr>
                <th>Uploader</th>
                <td>
                  {image.uploaded_by ? (
                    <a href={`/users/${encodeURIComponent(image.uploaded_by.username)}`}>{image.uploaded_by.username}</a>
                  ) : (
                    "unknown"
                  )}
                </td>
              </tr>
              <tr>
                <th>Rating</th>
                <td>{image.rating}</td>
              </tr>
              <tr>
                <th>Dimensions</th>
                <td>{image.width}x{image.height}</td>
              </tr>
              <tr>
                <th>Format</th>
                <td>{original?.mime_type ?? "unknown"}</td>
              </tr>
              <tr>
                <th>File size</th>
                <td>{originalFileSize}</td>
              </tr>
              <tr>
                <th>File</th>
                <td>{image.original_filename}</td>
              </tr>
              <tr>
                <th>Original</th>
                <td>
                  {original?.url ? (
                    <a href={original.url} rel="noreferrer" target="_blank">
                      Open original
                    </a>
                  ) : (
                    "unavailable"
                  )}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <aside className="post-sidebar">
        <section className="panel">
          <h2>Tags</h2>
          <div className="post-tag-groups">
            {orderedTagGroups.map((group) => {
              const collapsible = group.category === "general";
              const open = collapsible ? generalTagsOpen : true;
              return (
                <div className="post-tag-group" key={group.category}>
                  <div className="post-tag-group-head">
                    <h3>{group.label}</h3>
                    {collapsible ? (
                      <button
                        className="post-tag-toggle"
                        onClick={() => setGeneralTagsOpen((current) => !current)}
                        type="button"
                      >
                        {open ? "Hide" : `Show (${group.tags.length})`}
                      </button>
                    ) : null}
                  </div>
                  {open ? (
                    <div className="post-tag-list">
                      {group.tags.map((item) => (
                        <div className="post-tag-row" key={`${item.tag.id}-${item.source}`}>
                          <TagLink
                            className={`tag tag-${item.tag.category}${isStaff && item.rating_cue ? ` tag-rating-cue-${item.rating_cue}` : ""}`}
                            href={`/?q=${encodeURIComponent(item.tag.name_normalized)}`}
                            tagName={item.tag.name_normalized}
                          >
                            {item.tag.display_name}
                          </TagLink>
                          <span className="post-tag-meta">
                            {item.is_manual ? "manual" : item.source}
                            {item.confidence !== null ? ` · ${(item.confidence * 100).toFixed(0)}%` : ""}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="post-tag-collapsed-note">{group.tags.length} general tags hidden.</p>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      </aside>
    </div>
  );
}
