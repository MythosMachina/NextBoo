"use client";

import { useEffect, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type ModerationComment = {
  id: number;
  image_id: string;
  image_uuid_short: string;
  image_rating: "general" | "sensitive" | "questionable" | "explicit";
  body: string;
  score: number;
  is_flagged: boolean;
  author_username: string | null;
  created_at: string;
  updated_at: string;
};

export default function AdminCommentsPage() {
  const [comments, setComments] = useState<ModerationComment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyCommentId, setBusyCommentId] = useState<number | null>(null);

  async function loadComments() {
    const response = await authFetch("/api/v1/moderation/comments");
    if (!response.ok) {
      setError("Failed to load flagged comments.");
      return;
    }
    const payload = await response.json();
    setComments(payload.data);
  }

  useEffect(() => {
    loadComments();
  }, []);

  async function clearFlag(commentId: number) {
    setBusyCommentId(commentId);
    setError(null);
    const response = await authFetch(`/api/v1/moderation/comments/${commentId}/clear-flag`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
    });
    setBusyCommentId(null);
    if (!response.ok) {
      setError("Failed to clear comment flag.");
      return;
    }
    await loadComments();
  }

  return (
    <AdminShell title="Comments" description="Review automatically flagged comments and jump directly into the affected post discussion.">
      {error ? <p className="form-error">{error}</p> : null}
      <section className="panel">
        <h2>Flagged Comments</h2>
        <div className="table-wrap">
          <table className="simple-table">
            <thead>
              <tr>
                <th>Post</th>
                <th>Rating</th>
                <th>Author</th>
                <th>Score</th>
                <th>Comment</th>
                <th>Updated</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {comments.map((comment) => (
                <tr key={comment.id}>
                  <td><a href={`/posts/${comment.image_id}`}>#{comment.image_uuid_short}</a></td>
                  <td>{comment.image_rating}</td>
                  <td>{comment.author_username ?? "unknown"}</td>
                  <td>{comment.score}</td>
                  <td>{comment.body}</td>
                  <td>{new Date(comment.updated_at).toLocaleString()}</td>
                  <td>
                    <div className="row-actions">
                      <button
                        className="theme-toggle"
                        disabled={busyCommentId === comment.id}
                        onClick={() => clearFlag(comment.id)}
                        type="button"
                      >
                        Clear Flag
                      </button>
                      <a className="admin-inline-link" href={`/posts/${comment.image_id}#comment-${comment.id}`}>Open</a>
                    </div>
                  </td>
                </tr>
              ))}
              {!comments.length ? (
                <tr>
                  <td colSpan={7}>No flagged comments are waiting for moderation.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </AdminShell>
  );
}
