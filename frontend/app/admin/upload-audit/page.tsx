"use client";

import { useEffect, useMemo, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type UploadRequestAudit = {
  id: number;
  username: string;
  content_focus: string;
  reason: string;
  status: "approved" | "rejected";
  review_note: string | null;
  reviewed_by_username: string | null;
  reviewed_at: string | null;
};

export default function AdminUploadAuditPage() {
  const [items, setItems] = useState<UploadRequestAudit[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadAudit() {
      const [approvedResponse, rejectedResponse] = await Promise.all([
        authFetch("/api/v1/upload-requests?status=approved"),
        authFetch("/api/v1/upload-requests?status=rejected")
      ]);
      if (!approvedResponse.ok || !rejectedResponse.ok) {
        setError("Failed to load upload request audit.");
        return;
      }
      const approvedPayload = await approvedResponse.json();
      const rejectedPayload = await rejectedResponse.json();
      setItems([...approvedPayload.data, ...rejectedPayload.data].sort((a, b) => (a.reviewed_at < b.reviewed_at ? 1 : -1)));
    }

    loadAudit();
  }, []);

  return (
    <AdminShell title="Upload Audit" description="Processed upload requests retained as audit history.">
      {error ? <p className="form-error">{error}</p> : null}
      <section className="panel">
        <h2>Audit Log</h2>
        <div className="table-wrap">
          <table className="simple-table">
            <thead>
              <tr>
                <th>User</th>
                <th>Status</th>
                <th>Primary Content</th>
                <th>Reason</th>
                <th>Review</th>
                <th>Admin</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{item.username}</td>
                  <td>{item.status}</td>
                  <td>{item.content_focus}</td>
                  <td>{item.reason}</td>
                  <td>{item.review_note ?? "-"}</td>
                  <td>{item.reviewed_by_username ?? "-"}</td>
                </tr>
              ))}
              {!items.length ? (
                <tr>
                  <td colSpan={6}>No processed requests yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </AdminShell>
  );
}
