"use client";

import { useEffect, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch, useAuthState } from "../../components/auth";

type Job = {
  id: number;
  job_type: string;
  image_id: string | null;
  status: string;
  retry_count: number;
  max_retries: number;
  last_error: string | null;
  created_at: string;
  updated_at: string;
};

type JobOutcome = {
  job_id: number | null;
  import_batch_id: number | null;
  outcome: "accepted" | "duplicate" | "failed";
  message: string | null;
  image_id: string | null;
  created_at: string;
};

type JobsMeta = {
  count: number;
  page: number;
  limit: number;
  total_count: number;
  total_pages: number;
};

type Overview = {
  queue: Record<string, number>;
  displayed_total: number;
  recent_counts: Record<string, number>;
  recent_outcomes: JobOutcome[];
  tracked_outcomes: number;
};

const PAGE_SIZE = 10;

export default function AdminJobsPage() {
  const { isAdmin } = useAuthState();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [meta, setMeta] = useState<JobsMeta>({ count: 0, page: 1, limit: PAGE_SIZE, total_count: 0, total_pages: 1 });
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);

  async function loadOverview() {
    const response = await authFetch("/api/v1/jobs/overview");
    if (!response.ok) {
      setError("Failed to load live job overview.");
      return;
    }
    const payload = await response.json();
    setOverview(payload.data);
  }

  async function loadJobs(nextPage = page) {
    const response = await authFetch(`/api/v1/jobs?page=${nextPage}&limit=${PAGE_SIZE}`);
    if (!response.ok) {
      setError("Failed to load jobs.");
      return;
    }
    const payload = await response.json();
    setJobs(payload.data);
    setMeta(payload.meta);
  }

  async function loadData(nextPage = page) {
    await Promise.all([loadOverview(), loadJobs(nextPage)]);
  }

  async function requeue(jobId: number) {
    await authFetch(`/api/v1/jobs/${jobId}/requeue`, {
      method: "POST"
    });
    await loadData(page);
  }

  async function dismiss(jobId: number) {
    if (!window.confirm("Accept failure, end process and remove this job?")) {
      return;
    }
    await authFetch(`/api/v1/jobs/${jobId}/dismiss`, {
      method: "POST"
    });
    await loadData(page);
  }

  useEffect(() => {
    loadData(page);
  }, [page]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      loadData(page);
    }, 5000);
    return () => window.clearInterval(interval);
  }, [page]);

  function navigate(nextPage: number) {
    if (nextPage < 1 || nextPage > meta.total_pages) {
      return;
    }
    setPage(nextPage);
  }

  return (
    <AdminShell title="Jobs" description="Live ingest visibility with accepted, duplicate, failed and queue state.">
      {error ? <p className="form-error">{error}</p> : null}

      {overview ? (
        <div className="admin-stat-grid">
          <section className="panel">
            <h2>Accepted</h2>
            <div className="admin-stat-body">
              <strong>{overview.recent_counts.accepted ?? 0}</strong>
              <p>Recent uploads that became visible posts.</p>
            </div>
          </section>
          <section className="panel">
            <h2>Duplicates</h2>
            <div className="admin-stat-body">
              <strong>{overview.recent_counts.duplicate ?? 0}</strong>
              <p>Recent uploads dropped as duplicates.</p>
            </div>
          </section>
          <section className="panel">
            <h2>Failed</h2>
            <div className="admin-stat-body">
              <strong>{overview.recent_counts.failed ?? 0}</strong>
              <p>Recent uploads that failed or were dropped.</p>
            </div>
          </section>
          <section className="panel">
            <h2>Displayed</h2>
            <div className="admin-stat-body">
              <strong>{overview.displayed_total}</strong>
              <p>Posts currently visible in the database.</p>
            </div>
          </section>
          <section className="panel">
            <h2>Queued</h2>
            <div className="admin-stat-body">
              <strong>{overview.queue.queued ?? 0}</strong>
              <p>Jobs waiting in the ingest queue.</p>
            </div>
          </section>
          <section className="panel">
            <h2>Running</h2>
            <div className="admin-stat-body">
              <strong>{(overview.queue.running ?? 0) + (overview.queue.retrying ?? 0)}</strong>
              <p>Jobs currently processing or retrying.</p>
            </div>
          </section>
        </div>
      ) : null}

      <section className="panel">
        <h2>Recent Outcomes</h2>
        <p className="account-note">Live worker outcomes are refreshed every 5 seconds.</p>
        <div className="table-wrap">
          <table className="simple-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Outcome</th>
                <th>Image</th>
                <th>Job</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {overview?.recent_outcomes.length ? (
                overview.recent_outcomes.slice(0, 20).map((outcome, index) => (
                  <tr key={`${outcome.created_at}-${outcome.job_id ?? index}`}>
                    <td>{new Date(outcome.created_at).toLocaleString()}</td>
                    <td>{outcome.outcome}</td>
                    <td>{outcome.image_id ? <a href={`/posts/${outcome.image_id}`}>{outcome.image_id.slice(0, 8)}</a> : "-"}</td>
                    <td>{outcome.job_id ?? "-"}</td>
                    <td>{outcome.message ?? "-"}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5}>No recent worker outcomes yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="section-head-inline">
          <h2>Job Queue</h2>
          <div className="section-head-inline">
            <p className="account-note">
              {meta.total_count} jobs total
            </p>
            <div className="pagination-controls inline-pagination">
              <button className="page-number" disabled={page <= 1} onClick={() => navigate(page - 1)} type="button">
                Prev
              </button>
              <span className="page-number active">
                {meta.page} / {meta.total_pages}
              </span>
              <button className="page-number" disabled={page >= meta.total_pages} onClick={() => navigate(page + 1)} type="button">
                Next
              </button>
            </div>
          </div>
        </div>
        <div className="table-wrap">
          <table className="simple-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Status</th>
                <th>Type</th>
                <th>Image</th>
                <th>Retries</th>
                <th>Error</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td>{job.id}</td>
                  <td>{job.status}</td>
                  <td>{job.job_type}</td>
                  <td>{job.image_id ? <a href={`/posts/${job.image_id}`}>{job.image_id.slice(0, 8)}</a> : "-"}</td>
                  <td>{job.retry_count}/{job.max_retries}</td>
                  <td>{job.last_error ?? "-"}</td>
                  <td>
                    {job.status === "failed" ? (
                      isAdmin ? (
                        <div className="row-actions">
                          <button className="theme-toggle" onClick={() => requeue(job.id)} type="button">
                            Requeue
                          </button>
                          <button className="danger-button compact-danger" onClick={() => dismiss(job.id)} type="button">
                            Accept Failure
                          </button>
                        </div>
                      ) : (
                        "admin only"
                      )
                    ) : (
                      "-"
                    )}
                  </td>
                </tr>
              ))}
              {!jobs.length ? (
                <tr>
                  <td colSpan={7}>No active jobs.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </AdminShell>
  );
}
