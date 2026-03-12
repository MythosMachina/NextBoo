"use client";

import { useEffect, useMemo, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type UploadRequest = {
  id: number;
  username: string;
  user_id: number;
  content_focus: string;
  reason: string;
  status: "pending" | "approved" | "rejected";
  review_note: string | null;
  created_at: string;
};

export default function AdminUploadRequestsPage() {
  const [requests, setRequests] = useState<UploadRequest[]>([]);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);

  async function loadRequests() {
    const response = await authFetch("/api/v1/upload-requests?status=pending");
    if (!response.ok) {
      setError("Failed to load upload requests.");
      return;
    }
    const payload = await response.json();
    setRequests(payload.data);
  }

  useEffect(() => {
    loadRequests();
  }, []);

  async function reviewRequest(requestId: number, status: "approved" | "rejected") {
    setSavingId(requestId);
    setError(null);
    const response = await authFetch(`/api/v1/upload-requests/${requestId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        status,
        review_note: notes[requestId] || null
      })
    });
    setSavingId(null);
    if (!response.ok) {
      setError("Failed to process upload request.");
      return;
    }
    await loadRequests();
  }

  return (
    <AdminShell title="Upload Requests" description="Pending upload-permission requests waiting for admin approval.">
      {error ? <p className="form-error">{error}</p> : null}
      <section className="panel">
        <h2>Pending Requests</h2>
        <div className="table-wrap">
          <table className="simple-table">
            <thead>
              <tr>
                <th>User</th>
                <th>Primary Content</th>
                <th>Reason</th>
                <th>Review Note</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((request) => (
                <tr key={request.id}>
                  <td>{request.username}</td>
                  <td>{request.content_focus}</td>
                  <td>{request.reason}</td>
                  <td>
                    <textarea
                      className="stack-textarea"
                      onChange={(event) => setNotes((current) => ({ ...current, [request.id]: event.target.value }))}
                      rows={3}
                      value={notes[request.id] ?? ""}
                    />
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        className="theme-toggle"
                        disabled={savingId === request.id}
                        onClick={() => reviewRequest(request.id, "approved")}
                        type="button"
                      >
                        Approve
                      </button>
                      <button
                        className="theme-toggle"
                        disabled={savingId === request.id}
                        onClick={() => reviewRequest(request.id, "rejected")}
                        type="button"
                      >
                        Reject
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!requests.length ? (
                <tr>
                  <td colSpan={5}>No pending upload requests.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </AdminShell>
  );
}
