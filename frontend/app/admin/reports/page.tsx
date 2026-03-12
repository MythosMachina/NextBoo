"use client";

import { useEffect, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type ReportItem = {
  id: number;
  image_id: string;
  image_uuid_short: string;
  image_rating: "general" | "sensitive" | "questionable" | "explicit";
  image_visibility_status: "visible" | "hidden" | "deleted";
  reported_by_username: string | null;
  reason: string;
  message: string | null;
  status: "open" | "in_review" | "resolved" | "rejected";
  review_note: string | null;
  reviewed_by_username: string | null;
  created_at: string;
  reviewed_at: string | null;
};

export default function AdminReportsPage() {
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [decisions, setDecisions] = useState<Record<number, "visible" | "deleted">>({});

  async function loadReports() {
    const response = await authFetch("/api/v1/moderation/reports");
    if (!response.ok) {
      setError("Failed to load reports.");
      return;
    }
    const payload = await response.json();
    setReports(payload.data);
  }

  useEffect(() => {
    loadReports();
  }, []);

  async function updateStatus(report: ReportItem, nextStatus: ReportItem["status"]) {
    setSavingId(report.id);
    setError(null);
    if (nextStatus === "resolved" && !decisions[report.id]) {
      setError("Select a moderation decision before resolving a report.");
      setSavingId(null);
      return;
    }

    const response = await authFetch(`/api/v1/moderation/reports/${report.id}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ status: nextStatus })
    });
    if (!response.ok) {
      setSavingId(null);
      setError("Failed to update report.");
      return;
    }

    if (nextStatus === "resolved") {
      const visibilityStatus = decisions[report.id];
      const imageResponse =
        visibilityStatus === "deleted"
          ? await authFetch(`/api/v1/images/${report.image_id}/delete`, {
              method: "POST",
              headers: { "Content-Type": "application/json" }
            })
          : await authFetch(`/api/v1/images/${report.image_id}/visibility`, {
              method: "PATCH",
              headers: {
                "Content-Type": "application/json"
              },
              body: JSON.stringify({
                visibility_status: visibilityStatus,
                reason: "resolved_release"
              })
            });
      if (!imageResponse.ok) {
        setSavingId(null);
        setError("Report status updated, but image decision failed.");
        await loadReports();
        return;
      }
    }

    setSavingId(null);
    await loadReports();
  }

  return (
    <AdminShell title="Reports" description="User flags that require moderator or admin review.">
      {error ? <p className="form-error">{error}</p> : null}
      <section className="panel">
        <h2>Open and Recent Reports</h2>
        <div className="table-wrap">
          <table className="simple-table">
            <thead>
              <tr>
                <th>Post</th>
                <th>Status</th>
                <th>Reason</th>
                <th>Reporter</th>
                <th>Message</th>
                <th>Visibility</th>
                <th>Decision</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((report) => (
                <tr key={report.id}>
                  <td><a href={`/admin/content/${report.image_id}`}>#{report.image_uuid_short}</a></td>
                  <td>{report.status}</td>
                  <td>{report.reason}</td>
                  <td>{report.reported_by_username ?? "unknown"}</td>
                  <td>{report.message ?? "-"}</td>
                  <td>{report.image_visibility_status}</td>
                  <td>
                    <select
                      className="stack-select"
                      disabled={savingId === report.id || report.status === "resolved" || report.status === "rejected"}
                      onChange={(event) =>
                        setDecisions((current) => ({
                          ...current,
                          [report.id]: event.target.value as "visible" | "deleted"
                        }))
                      }
                      value={decisions[report.id] ?? ""}
                    >
                      <option value="">Select</option>
                      <option value="visible">Release</option>
                      <option value="deleted">Delete</option>
                    </select>
                  </td>
                  <td>
                    <div className="row-actions">
                      {report.status !== "in_review" ? (
                        <button
                          className="theme-toggle"
                          disabled={savingId === report.id}
                          onClick={() => updateStatus(report, "in_review")}
                          type="button"
                        >
                          Review
                        </button>
                      ) : null}
                      {report.status !== "resolved" ? (
                        <button
                          className="theme-toggle"
                          disabled={savingId === report.id}
                          onClick={() => updateStatus(report, "resolved")}
                          type="button"
                        >
                          Resolve
                        </button>
                      ) : null}
                      {report.status !== "rejected" ? (
                        <button
                          className="theme-toggle"
                          disabled={savingId === report.id}
                          onClick={() => updateStatus(report, "rejected")}
                          type="button"
                        >
                          Reject
                        </button>
                      ) : null}
                      <a className="admin-inline-link" href={`/admin/content/${report.image_id}`}>Open</a>
                    </div>
                  </td>
                </tr>
              ))}
              {!reports.length ? (
                <tr>
                  <td colSpan={8}>No reports found.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </AdminShell>
  );
}
