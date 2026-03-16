"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type NearDuplicateItem = {
  id: number;
  image_id: string;
  similar_image_id: string;
  image_uuid_short: string;
  similar_image_uuid_short: string;
  hamming_distance: number;
  status: string;
  created_at: string;
};

export default function AdminNearDuplicatesPage() {
  const [items, setItems] = useState<NearDuplicateItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function loadItems() {
    const response = await authFetch("/api/v1/moderation/near-duplicates");
    if (!response.ok) {
      setError("Failed to load near duplicate reviews.");
      return;
    }
    const payload = await response.json();
    setItems(payload.data);
  }

  useEffect(() => {
    loadItems();
  }, []);

  async function updateStatus(reviewId: number, action: "dismissed" | "confirmed") {
    const response = await authFetch(`/api/v1/moderation/near-duplicates/${reviewId}?action=${action}`, {
      method: "PATCH",
    });
    if (!response.ok) {
      setError("Failed to update near duplicate review.");
      return;
    }
    await loadItems();
  }

  return (
    <AdminShell
      title="Near Duplicates"
      description="Review perceptual-hash matches that are close enough for staff attention without auto-merging or auto-dropping them."
    >
      {error ? <p className="form-error">{error}</p> : null}
      <section className="panel">
        <h2>Open Matches</h2>
        <div className="table-wrap">
          <table className="simple-table">
            <thead>
              <tr>
                <th>Left</th>
                <th>Right</th>
                <th>Distance</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td><Link href={`/posts/${item.image_id}`}>{item.image_uuid_short}</Link></td>
                  <td><Link href={`/posts/${item.similar_image_id}`}>{item.similar_image_uuid_short}</Link></td>
                  <td>{item.hamming_distance}</td>
                  <td>{item.status}</td>
                  <td className="inline-action-row">
                    <button className="secondary-button" onClick={() => updateStatus(item.id, "dismissed")} type="button">
                      Dismiss
                    </button>
                    <button className="primary-button" onClick={() => updateStatus(item.id, "confirmed")} type="button">
                      Confirm
                    </button>
                  </td>
                </tr>
              ))}
              {!items.length ? (
                <tr>
                  <td colSpan={5}>No near duplicate reviews.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </AdminShell>
  );
}
