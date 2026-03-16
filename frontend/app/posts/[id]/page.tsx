"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
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
  duration_seconds?: number | null;
  frame_rate?: number | null;
  has_audio?: boolean;
  video_codec?: string | null;
  audio_codec?: string | null;
  rating: "general" | "sensitive" | "questionable" | "explicit";
  visibility_status: "visible" | "hidden" | "deleted";
  uploaded_by: {
    id: number;
    username: string;
  } | null;
  vote_score: number;
  current_user_vote: number | null;
  vote_cooldown_remaining_seconds: number;
  variants: Variant[];
  tags: TagItem[];
  comments: {
    id: number;
    body: string;
    is_edited: boolean;
    is_flagged: boolean;
    score: number;
    current_user_vote: number | null;
    created_at: string;
    updated_at: string;
    author: {
      id: number;
      username: string;
    };
    replies: {
      id: number;
      body: string;
      is_edited: boolean;
      is_flagged: boolean;
      score: number;
      current_user_vote: number | null;
      created_at: string;
      updated_at: string;
      author: {
        id: number;
        username: string;
      };
      replies: [];
    }[];
  }[];
};

type RelatedPost = {
  id: string;
  uuid_short: string;
  original_filename: string;
  thumb_url: string | null;
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

function resolveMediaBadge(
  filename: string,
  mimeType: string | undefined,
  durationSeconds: number | null | undefined
): "IMAGE" | "ANIMATION" | "VIDEO" {
  if (mimeType?.startsWith("video/")) {
    return "VIDEO";
  }
  const extension = filename.split(".").pop()?.toLowerCase() ?? "";
  if (["mp4", "mkv", "webm"].includes(extension)) {
    return "VIDEO";
  }
  if ((durationSeconds ?? 0) > 0) {
    return "ANIMATION";
  }
  return "IMAGE";
}

export default function PostDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { authenticated, isAdmin, isStaff } = useAuthState();
  const [image, setImage] = useState<ImageDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [generalTagsOpen, setGeneralTagsOpen] = useState(false);
  const [voteBusy, setVoteBusy] = useState(false);
  const [voteMessage, setVoteMessage] = useState<string | null>(null);
  const [commentBody, setCommentBody] = useState("");
  const [commentBusy, setCommentBusy] = useState(false);
  const [commentMessage, setCommentMessage] = useState<string | null>(null);
  const [replyDrafts, setReplyDrafts] = useState<Record<number, string>>({});
  const [replyOpen, setReplyOpen] = useState<Record<number, boolean>>({});
  const [commentVoteBusy, setCommentVoteBusy] = useState<Record<number, boolean>>({});
  const [editingCommentId, setEditingCommentId] = useState<number | null>(null);
  const [editingBody, setEditingBody] = useState("");
  const [editingReason, setEditingReason] = useState("");
  const [relatedPosts, setRelatedPosts] = useState<RelatedPost[]>([]);

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
      const relatedResponse = await authFetch(`/api/v1/images/${params.id}/related`, { cache: "no-store" });
      if (relatedResponse.ok) {
        const relatedPayload = await relatedResponse.json();
        setRelatedPosts(relatedPayload.data);
      } else {
        setRelatedPosts([]);
      }
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
  const thumb = image.variants.find((variant) => variant.variant_type === "thumb");
  const originalFileSize = original ? `${(original.file_size / (1024 * 1024)).toFixed(2)} MB` : "unknown";
  const mediaBadge = resolveMediaBadge(image.original_filename, original?.mime_type, image.duration_seconds);
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

  async function handleVote(value: -1 | 1) {
    if (!image || voteBusy || !authenticated) {
      return;
    }
    setVoteBusy(true);
    setVoteMessage(null);
    const response = await authFetch(`/api/v1/images/${image.id}/vote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value }),
    });
    setVoteBusy(false);
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = payload?.detail;
      if (detail?.retry_after_seconds) {
        setVoteMessage(`Cooldown active: ${detail.retry_after_seconds}s`);
      } else {
        setVoteMessage(detail?.message ?? detail ?? "Vote failed.");
      }
      return;
    }
    setImage((current) =>
      current
        ? {
            ...current,
            vote_score: payload.data.vote_score,
            current_user_vote: payload.data.current_user_vote,
            vote_cooldown_remaining_seconds: payload.data.vote_cooldown_remaining_seconds,
          }
        : current
    );
    setVoteMessage(
      payload.data.vote_cooldown_remaining_seconds > 0
        ? `Vote recorded. Cooldown: ${payload.data.vote_cooldown_remaining_seconds}s`
        : "Vote recorded."
    );
  }

  async function handleCommentSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!image || !authenticated || commentBusy || !commentBody.trim()) {
      return;
    }
    setCommentBusy(true);
    setCommentMessage(null);
    const response = await authFetch(`/api/v1/images/${image.id}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: commentBody.trim() }),
    });
    const payload = await response.json().catch(() => null);
    setCommentBusy(false);
    if (!response.ok) {
      setCommentMessage(payload?.detail ?? "Comment failed.");
      return;
    }
    setImage((current) =>
      current
        ? {
            ...current,
            comments: [...current.comments, payload.data],
          }
        : current
    );
    setCommentBody("");
    setCommentMessage("Comment posted.");
  }

  async function handleReplySubmit(parentCommentId: number) {
    if (!image || !authenticated) {
      return;
    }
    const body = (replyDrafts[parentCommentId] ?? "").trim();
    if (!body) {
      return;
    }
    setCommentBusy(true);
    setCommentMessage(null);
    const response = await authFetch(`/api/v1/images/${image.id}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body, parent_comment_id: parentCommentId }),
    });
    const payload = await response.json().catch(() => null);
    setCommentBusy(false);
    if (!response.ok) {
      setCommentMessage(payload?.detail ?? "Reply failed.");
      return;
    }
    setImage((current) =>
      current
        ? {
            ...current,
            comments: current.comments.map((comment) =>
              comment.id === parentCommentId
                ? { ...comment, replies: [...comment.replies, payload.data] }
                : comment
            ),
          }
        : current
    );
    setReplyDrafts((current) => ({ ...current, [parentCommentId]: "" }));
    setReplyOpen((current) => ({ ...current, [parentCommentId]: false }));
  }

  async function handleCommentVote(commentId: number, value: -1 | 1) {
    if (!image || !authenticated || commentVoteBusy[commentId]) {
      return;
    }
    setCommentVoteBusy((current) => ({ ...current, [commentId]: true }));
    setCommentMessage(null);
    const response = await authFetch(`/api/v1/images/${image.id}/comments/${commentId}/vote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value }),
    });
    const payload = await response.json().catch(() => null);
    setCommentVoteBusy((current) => ({ ...current, [commentId]: false }));
    if (!response.ok) {
      const detail = payload?.detail;
      setCommentMessage(detail?.message ?? detail ?? "Comment vote failed.");
      return;
    }
    const patchComment = (comment: ImageDetail["comments"][number]) =>
      comment.id === commentId
        ? {
            ...comment,
            score: payload.data.score,
            current_user_vote: payload.data.current_user_vote,
            is_flagged: payload.data.is_flagged,
          }
        : { ...comment, replies: comment.replies.map((reply) => (reply.id === commentId ? { ...reply, score: payload.data.score, current_user_vote: payload.data.current_user_vote, is_flagged: payload.data.is_flagged } : reply)) };
    setImage((current) =>
      current
        ? {
            ...current,
            comments: current.comments.map(patchComment),
          }
        : current
    );
  }

  async function handleDeleteComment(commentId: number) {
    if (!image || !isStaff) {
      return;
    }
    if (!window.confirm("Delete this comment?")) {
      return;
    }
    const response = await authFetch(`/api/v1/images/${image.id}/comments/${commentId}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      setCommentMessage("Delete failed.");
      return;
    }
    setImage((current) =>
      current
        ? {
            ...current,
            comments: current.comments
              .filter((comment) => comment.id !== commentId)
              .map((comment) => ({ ...comment, replies: comment.replies.filter((reply) => reply.id !== commentId) })),
          }
        : current
    );
  }

  async function handleEditComment(commentId: number) {
    if (!image || !isStaff || !editingBody.trim()) {
      return;
    }
    const response = await authFetch(`/api/v1/images/${image.id}/comments/${commentId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: editingBody.trim(), moderation_reason: editingReason.trim() || undefined }),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      setCommentMessage(payload?.detail ?? "Edit failed.");
      return;
    }
    setCommentMessage("Comment updated.");
    setEditingCommentId(null);
    await (async () => {
      const refreshed = await authFetch(`/api/v1/images/${image.id}`, { cache: "no-store" });
      if (refreshed.ok) {
        const refreshedPayload = await refreshed.json();
        setImage(refreshedPayload.data);
      }
    })();
  }

  function startEditComment(commentId: number, body: string) {
    setEditingCommentId(commentId);
    setEditingBody(body);
    setEditingReason("");
  }

  function renderComment(
    comment: ImageDetail["comments"][number] | ImageDetail["comments"][number]["replies"][number],
    isReply = false
  ) {
    const isEditing = editingCommentId === comment.id;
    return (
      <article className={`post-comment${isReply ? " is-reply" : ""}${comment.is_flagged ? " is-flagged" : ""}`} key={comment.id}>
        <div className="post-comment-head">
          <a href={`/users/${encodeURIComponent(comment.author.username)}`}>{comment.author.username}</a>
          <span>{new Date(comment.created_at).toLocaleString()}</span>
        </div>
        {isEditing ? (
          <div className="stack-form">
            <label>
              Edit comment
              <textarea className="stack-textarea" onChange={(event) => setEditingBody(event.target.value)} rows={4} value={editingBody} />
            </label>
            <label>
              Moderation reason
              <input className="stack-input" onChange={(event) => setEditingReason(event.target.value)} type="text" value={editingReason} />
            </label>
            <div className="post-comment-actions">
              <button className="primary-button" onClick={() => handleEditComment(comment.id)} type="button">Save edit</button>
              <button className="vote-button" onClick={() => setEditingCommentId(null)} type="button">Cancel</button>
            </div>
          </div>
        ) : (
          <p>{comment.body}</p>
        )}
        <div className="post-comment-actions">
          <span className="post-comment-score">{comment.score}</span>
          <button
            className={`vote-button${comment.current_user_vote === 1 ? " active-up" : ""}`}
            disabled={!authenticated || Boolean(commentVoteBusy[comment.id])}
            onClick={() => handleCommentVote(comment.id, 1)}
            type="button"
          >
            👍
          </button>
          <button
            className={`vote-button${comment.current_user_vote === -1 ? " active-down" : ""}`}
            disabled={!authenticated || Boolean(commentVoteBusy[comment.id])}
            onClick={() => handleCommentVote(comment.id, -1)}
            type="button"
          >
            👎
          </button>
          {!isReply && authenticated ? (
            <button className="vote-button" onClick={() => setReplyOpen((current) => ({ ...current, [comment.id]: !current[comment.id] }))} type="button">
              Reply
            </button>
          ) : null}
          {isStaff ? (
            <>
              <button className="vote-button" onClick={() => startEditComment(comment.id, comment.body)} type="button">Edit</button>
              <button className="danger-button compact-danger" onClick={() => handleDeleteComment(comment.id)} type="button">Delete</button>
            </>
          ) : null}
          {comment.is_flagged ? <span className="comment-flag-badge">Flagged</span> : null}
        </div>
        {!isReply && replyOpen[comment.id] ? (
          <div className="stack-form post-reply-form">
            <label>
              Reply
              <textarea
                className="stack-textarea"
                onChange={(event) => setReplyDrafts((current) => ({ ...current, [comment.id]: event.target.value }))}
                rows={3}
                value={replyDrafts[comment.id] ?? ""}
              />
            </label>
            <div className="post-comment-actions">
              <button className="primary-button" onClick={() => handleReplySubmit(comment.id)} type="button">Post reply</button>
              <button className="vote-button" onClick={() => setReplyOpen((current) => ({ ...current, [comment.id]: false }))} type="button">Cancel</button>
            </div>
          </div>
        ) : null}
        {comment.replies.length ? (
          <div className="post-comment-replies">
            {comment.replies.map((reply) => renderComment(reply, true))}
          </div>
        ) : null}
      </article>
    );
  }

  return (
    <div className="post-detail-layout">
      <section className="post-view panel">
        <h2>Post</h2>
        <div className="post-view-inner">
          <div className="post-media-banner">
            <span className="post-media-badge">{mediaBadge}</span>
          </div>
          {original?.url ? (
            original.mime_type.startsWith("video/") ? (
              <video className="post-full-image" controls loop playsInline poster={thumb?.url ?? undefined} src={original.url} />
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
                <th>Media type</th>
                <td>{mediaBadge}</td>
              </tr>
              <tr>
                <th>Format</th>
                <td>{original?.mime_type ?? "unknown"}</td>
              </tr>
              {image.duration_seconds ? (
                <tr>
                  <th>Duration</th>
                  <td>{image.duration_seconds.toFixed(1)}s</td>
                </tr>
              ) : null}
              {image.frame_rate ? (
                <tr>
                  <th>Frame rate</th>
                  <td>{image.frame_rate.toFixed(2)} fps</td>
                </tr>
              ) : null}
              {image.video_codec ? (
                <tr>
                  <th>Video codec</th>
                  <td>{image.video_codec}</td>
                </tr>
              ) : null}
              {image.has_audio ? (
                <tr>
                  <th>Audio</th>
                  <td>{image.audio_codec ? `Yes (${image.audio_codec})` : "Yes"}</td>
                </tr>
              ) : null}
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
              <tr>
                <th>Rating score</th>
                <td>
                  <div className="post-vote-row">
                    <span className="post-vote-score">{image.vote_score}</span>
                    <button
                      className={`vote-button${image.current_user_vote === 1 ? " active-up" : ""}`}
                      disabled={voteBusy || !authenticated}
                      onClick={() => handleVote(1)}
                      type="button"
                    >
                      👍
                    </button>
                    <button
                      className={`vote-button${image.current_user_vote === -1 ? " active-down" : ""}`}
                      disabled={voteBusy || !authenticated}
                      onClick={() => handleVote(-1)}
                      type="button"
                    >
                      👎
                    </button>
                  </div>
                  {voteMessage ? <div className="post-vote-note">{voteMessage}</div> : null}
                  {!authenticated ? <div className="post-vote-note">Login required to vote.</div> : null}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <section className="panel post-comments-panel">
          <h2>Comments</h2>
          <div className="post-comments-list">
            {image.comments.length ? (
              image.comments.map((comment) => renderComment(comment))
            ) : (
              <div className="empty-state compact-empty">
                <strong>No comments</strong>
                <p>No one has commented on this post yet.</p>
              </div>
            )}
          </div>
          {authenticated ? (
            <form className="stack-form" onSubmit={handleCommentSubmit}>
              <label>
                Add comment
                <textarea
                  className="stack-textarea"
                  onChange={(event) => setCommentBody(event.target.value)}
                  placeholder="Write a comment"
                  rows={4}
                  value={commentBody}
                />
              </label>
              <button className="primary-button" disabled={commentBusy || !commentBody.trim()} type="submit">
                {commentBusy ? "Posting..." : "Post comment"}
              </button>
              {commentMessage ? <p className="form-success">{commentMessage}</p> : null}
            </form>
          ) : (
            <p className="post-vote-note">Login required to comment.</p>
          )}
        </section>

        <section className="panel">
          <h2>Related Images</h2>
          {relatedPosts.length ? (
            <div className="post-related-grid">
              {relatedPosts.map((post) => (
                <Link className="post-related-card" href={`/posts/${post.id}`} key={post.id}>
                  {post.thumb_url ? <img alt={post.original_filename} src={post.thumb_url} /> : null}
                  <span>{post.uuid_short}</span>
                </Link>
              ))}
            </div>
          ) : (
            <div className="empty-state compact-empty">
              <strong>No related images</strong>
              <p>No strong shared-tag matches were found.</p>
            </div>
          )}
        </section>
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
