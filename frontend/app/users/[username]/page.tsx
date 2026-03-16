"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { authFetch } from "../../components/auth";

type UserProfile = {
  data: {
    id: number;
    username: string;
    role: "admin" | "moderator" | "uploader";
    created_at: string;
  };
  uploads: Array<{
    id: string;
    uuid_short: string;
    original_filename: string;
    width: number;
    height: number;
    rating: "general" | "sensitive" | "questionable" | "explicit";
    processing_status: string;
    created_at: string;
  thumb_url: string | null;
  preview_url?: string | null;
  preview_mime_type?: string | null;
  }>;
  meta: {
    count: number;
    limit: number;
  };
};

function ratingCode(rating: "general" | "sensitive" | "questionable" | "explicit"): string {
  if (rating === "sensitive") return "s";
  if (rating === "questionable") return "q";
  if (rating === "explicit") return "x";
  return "g";
}

export default function UserProfilePage() {
  const params = useParams<{ username: string }>();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadProfile() {
      const response = await authFetch(`/api/v1/users/profile/${encodeURIComponent(params.username)}?limit=48`);
      if (!response.ok) {
        setError("Failed to load profile.");
        return;
      }
      const payload = await response.json();
      setProfile(payload);
    }

    loadProfile();
  }, [params.username]);

  if (!profile) {
    return (
      <div className="empty-state">
        <strong>Loading profile.</strong>
        <p>{error ?? "Fetching uploads and profile data."}</p>
      </div>
    );
  }

  return (
    <>
      <section className="panel">
        <h2>Profile</h2>
        <div className="account-card">
          <div className="account-row">
            <strong>User</strong>
            <span>{profile.data.username}</span>
          </div>
          <div className="account-row">
            <strong>Role</strong>
            <span>{profile.data.role}</span>
          </div>
          <div className="account-row">
            <strong>Uploads</strong>
            <span>{profile.meta.count}</span>
          </div>
        </div>
      </section>

      <section className="panel">
        <h2>Uploads</h2>
        {profile.uploads.length ? (
          <div className="thumb-grid">
            {profile.uploads.map((post) => (
              <article className="thumb-card" key={post.id}>
                <a className="thumb-frame" href={`/posts/${post.id}`}>
                  <span className={`rating rating-${ratingCode(post.rating)}`}>{ratingCode(post.rating)}</span>
                  {post.thumb_url ? (
                    <>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img alt={post.original_filename} className="thumb-image" loading="lazy" src={post.thumb_url} />
                      {post.preview_url ? (
                        <video
                          autoPlay
                          aria-hidden="true"
                          className="thumb-preview"
                          loop
                          muted
                          playsInline
                          preload="none"
                          src={post.preview_url}
                        />
                      ) : null}
                    </>
                  ) : (
                    <div className="thumb-art" />
                  )}
                </a>
                <div className="thumb-caption">
                  <div className="thumb-stats">
                    <span>{post.width}x{post.height}</span>
                    <span>{post.rating}</span>
                  </div>
                  <p>
                    Uploader: <a href={`/users/${encodeURIComponent(profile.data.username)}`}>{profile.data.username}</a>
                  </p>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <strong>No uploads found.</strong>
            <p>This user has no visible posts yet.</p>
          </div>
        )}
      </section>
    </>
  );
}
