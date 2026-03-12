"use client";

import { useEffect, useState } from "react";
import { AdminShell } from "../components/admin-shell";
import { authFetch } from "../components/auth";

type Stats = {
  imports: number;
  users: number;
  reports: number;
  flagged: number;
  uploadRequests: number;
};

type Overview = {
  queue: Record<string, number>;
  displayed_total: number;
  recent_counts: Record<string, number>;
  recent_outcomes: Array<{
    job_id: number | null;
    import_batch_id: number | null;
    outcome: "accepted" | "duplicate" | "failed";
    message: string | null;
    image_id: string | null;
    created_at: string;
  }>;
};

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<Stats>({ imports: 0, users: 0, reports: 0, flagged: 0, uploadRequests: 0 });
  const [overview, setOverview] = useState<Overview | null>(null);

  useEffect(() => {
    async function loadStats() {
      const [overviewResponse, importsResponse, usersResponse, reportsResponse, flaggedResponse, uploadRequestsResponse] = await Promise.all([
        authFetch("/api/v1/jobs/overview"),
        authFetch("/api/v1/jobs/imports?limit=1&page=1"),
        authFetch("/api/v1/users"),
        authFetch("/api/v1/moderation/reports"),
        authFetch("/api/v1/moderation/images"),
        authFetch("/api/v1/upload-requests?status=pending"),
      ]);

      if (overviewResponse.ok) {
        const payload = await overviewResponse.json();
        setOverview(payload.data);
      }

      const nextStats = { imports: 0, users: 0, reports: 0, flagged: 0, uploadRequests: 0 };
      if (importsResponse.ok) {
        const payload = await importsResponse.json();
        nextStats.imports = payload.meta.total_count ?? payload.meta.count ?? payload.data.length;
      }
      if (usersResponse.ok) {
        const payload = await usersResponse.json();
        nextStats.users = payload.meta.count ?? payload.data.length;
      }
      if (reportsResponse.ok) {
        const payload = await reportsResponse.json();
        nextStats.reports = payload.meta.count ?? payload.data.length;
      }
      if (flaggedResponse.ok) {
        const payload = await flaggedResponse.json();
        nextStats.flagged = payload.meta.count ?? payload.data.length;
      }
      if (uploadRequestsResponse.ok) {
        const payload = await uploadRequestsResponse.json();
        nextStats.uploadRequests = payload.meta.count ?? payload.data.length;
      }
      setStats(nextStats);
    }

    loadStats();
    const interval = window.setInterval(loadStats, 5000);
    return () => window.clearInterval(interval);
  }, []);

  return (
    <AdminShell title="Dashboard" description="Administrative entry point with live ingest and moderation counters.">
      <div className="admin-stat-grid">
        <section className="panel">
          <h2>Accepted</h2>
          <div className="admin-stat-body">
            <strong>{overview?.recent_counts.accepted ?? 0}</strong>
            <p>Recent uploads that became visible posts.</p>
          </div>
        </section>
        <section className="panel">
          <h2>Duplicates</h2>
          <div className="admin-stat-body">
            <strong>{overview?.recent_counts.duplicate ?? 0}</strong>
            <p>Recent uploads that matched existing media.</p>
          </div>
        </section>
        <section className="panel">
          <h2>Failed</h2>
          <div className="admin-stat-body">
            <strong>{overview?.recent_counts.failed ?? 0}</strong>
            <p>Recent uploads that failed processing or were dropped.</p>
          </div>
        </section>
        <section className="panel">
          <h2>Displayed Posts</h2>
          <div className="admin-stat-body">
            <strong>{overview?.displayed_total ?? 0}</strong>
            <p>Posts currently visible in the image index.</p>
          </div>
        </section>
        <section className="panel">
          <h2>Queue</h2>
          <div className="admin-stat-body">
            <strong>{overview ? (overview.queue.queued ?? 0) + (overview.queue.running ?? 0) + (overview.queue.retrying ?? 0) : 0}</strong>
            <p>Queued, running and retrying jobs combined.</p>
          </div>
        </section>
        <section className="panel">
          <h2>Imports</h2>
          <div className="admin-stat-body">
            <strong>{stats.imports}</strong>
            <p>Tracked import batches currently in the system.</p>
          </div>
        </section>
        <section className="panel">
          <h2>Users</h2>
          <div className="admin-stat-body">
            <strong>{stats.users}</strong>
            <p>Registered accounts available for review and maintenance.</p>
          </div>
        </section>
        <section className="panel">
          <h2>Reports</h2>
          <div className="admin-stat-body">
            <strong>{stats.reports}</strong>
            <p>User-submitted moderation reports awaiting triage.</p>
          </div>
        </section>
        <section className="panel">
          <h2>Flagged Content</h2>
          <div className="admin-stat-body">
            <strong>{stats.flagged}</strong>
            <p>Posts with reports or moderated visibility state.</p>
          </div>
        </section>
        <section className="panel">
          <h2>Upload Requests</h2>
          <div className="admin-stat-body">
            <strong>{stats.uploadRequests}</strong>
            <p>Pending user requests for upload access.</p>
          </div>
        </section>
      </div>
    </AdminShell>
  );
}
