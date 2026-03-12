"use client";

import { useEffect, useMemo, useState } from "react";
import { AccountShell } from "../../components/account-shell";
import { authFetch, useAuthState } from "../../components/auth";

type UploadItem = {
  id: string;
  uuid_short: string;
  original_filename: string;
  rating: "general" | "sensitive" | "questionable" | "explicit";
  visibility_status: "visible" | "hidden" | "deleted";
  created_at: string;
};

export default function AccountUploadsPage() {
  const { user } = useAuthState();
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadUploads() {
      if (!user) {
        return;
      }
      const response = await authFetch(`/api/v1/users/me/uploads?limit=100`, { cache: "no-store" });
      if (!response.ok) {
        setError("Failed to load your uploads.");
        return;
      }
      const payload = await response.json();
      setUploads(payload.uploads);
    }

    loadUploads();
  }, [user]);

  if (!user) {
    return (
      <AccountShell title="My Uploads" description="Review and manage posts that belong to your account.">
        <section className="panel">
          <h2>My Uploads</h2>
          <div className="empty-state">
            <strong>Login required.</strong>
            <p>Sign in to manage your own posts.</p>
          </div>
        </section>
      </AccountShell>
    );
  }

  return (
    <AccountShell title="My Uploads" description="Review and manage posts that belong to your account.">
      <section className="panel">
        <h2>My Uploads</h2>
        {error ? <p className="form-error">{error}</p> : null}
        <div className="table-wrap">
          <table className="simple-table">
            <thead>
              <tr>
                <th>Post</th>
                <th>Rating</th>
                <th>Visibility</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {uploads.map((upload) => (
                <tr key={upload.id}>
                  <td>#{upload.uuid_short} {upload.original_filename}</td>
                  <td>{upload.rating}</td>
                  <td>{upload.visibility_status}</td>
                  <td><a href={`/account/uploads/${upload.id}`}>Manage</a></td>
                </tr>
              ))}
              {!uploads.length ? (
                <tr>
                  <td colSpan={4}>You have not uploaded any visible posts yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </AccountShell>
  );
}
