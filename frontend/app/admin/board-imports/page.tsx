"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type BoardItem = {
  name: string;
  family: string;
  site_url: string;
};

type BoardImportEvent = {
  id: number;
  level: string;
  event_type: string;
  message: string;
  remote_post_id: string | null;
  job_id: number | null;
  image_id: string | null;
  is_error: boolean;
  created_at: string;
};

type BoardImportRun = {
  id: number;
  board_name: string;
  tag_query: string;
  requested_limit: number;
  hourly_limit: number;
  status: string;
  discovered_posts: number;
  downloaded_posts: number;
  queued_posts: number;
  completed_posts: number;
  duplicate_posts: number;
  skipped_posts: number;
  failed_posts: number;
  current_message: string | null;
  error_summary: string | null;
  source_import_batch_id: number | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  last_event_at: string | null;
};

type BoardImportRunDetail = BoardImportRun & {
  events: BoardImportEvent[];
};

const ACTIVE_STATUSES = new Set(["pending", "running", "retrying"]);

export default function AdminBoardImportsPage() {
  const [boards, setBoards] = useState<BoardItem[]>([]);
  const [runs, setRuns] = useState<BoardImportRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [selectedRun, setSelectedRun] = useState<BoardImportRunDetail | null>(null);
  const [boardName, setBoardName] = useState("");
  const [tags, setTags] = useState("");
  const [requestedLimit, setRequestedLimit] = useState(25);
  const [allBoards, setAllBoards] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionRunId, setActionRunId] = useState<number | null>(null);
  const [bulkAction, setBulkAction] = useState<string | null>(null);

  const selectedRunIsActive = useMemo(() => Boolean(selectedRun && ACTIVE_STATUSES.has(selectedRun.status)), [selectedRun]);

  async function loadBoardsAndRuns() {
    const [boardsResponse, runsResponse] = await Promise.all([
      authFetch("/api/v1/admin/board-imports/boards", { cache: "no-store" }),
      authFetch("/api/v1/admin/board-imports/runs?limit=20", { cache: "no-store" }),
    ]);

    if (!boardsResponse.ok || !runsResponse.ok) {
      setError("Failed to load board importer state.");
      setLoading(false);
      return;
    }

    const boardsPayload = await boardsResponse.json();
    const runsPayload = await runsResponse.json();
    const nextBoards = boardsPayload.data as BoardItem[];
    const nextRuns = runsPayload.data as BoardImportRun[];

    setBoards(nextBoards);
    setRuns(nextRuns);
    if (!boardName && nextBoards.length) {
      setBoardName(nextBoards[0].name);
    }
    if (nextRuns.length && selectedRunId == null) {
      setSelectedRunId(nextRuns[0].id);
    }
    setLoading(false);
  }

  async function loadRunDetail(runId: number) {
    const response = await authFetch(`/api/v1/admin/board-imports/runs/${runId}`, { cache: "no-store" });
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    setSelectedRun(payload.data as BoardImportRunDetail);
  }

  useEffect(() => {
    loadBoardsAndRuns();
  }, []);

  useEffect(() => {
    if (selectedRunId == null) {
      setSelectedRun(null);
      return;
    }
    loadRunDetail(selectedRunId);
  }, [selectedRunId]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      loadBoardsAndRuns();
      if (selectedRunId != null) {
        loadRunDetail(selectedRunId);
      }
    }, selectedRunIsActive ? 3000 : 8000);
    return () => window.clearInterval(intervalId);
  }, [selectedRunId, selectedRunIsActive]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    const response = await authFetch("/api/v1/admin/board-imports/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        board_name: boardName,
        tags,
        requested_limit: requestedLimit,
        all_boards: allBoards,
      }),
    });
    setSaving(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? "Failed to start board import.");
      return;
    }
    const payload = await response.json();
    const nextRun = payload.data as BoardImportRunDetail;
    const queuedCount = Number(payload?.meta?.queued_count ?? 1);
    setSelectedRunId(nextRun.id);
    setSelectedRun(nextRun);
    setMessage(
      allBoards
        ? `Queued ${queuedCount} board imports. Showing run #${nextRun.id}.`
        : `Queued board import #${nextRun.id}.`,
    );
    await loadBoardsAndRuns();
  }

  async function runAction(runId: number, action: "stop" | "retry" | "remove") {
    setActionRunId(runId);
    setError(null);
    setMessage(null);
    const endpoint =
      action === "remove"
        ? `/api/v1/admin/board-imports/runs/${runId}`
        : `/api/v1/admin/board-imports/runs/${runId}/${action}`;
    const response = await authFetch(endpoint, {
      method: action === "remove" ? "DELETE" : "POST",
    });
    setActionRunId(null);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? `Failed to ${action} run #${runId}.`);
      return;
    }

    if (action === "remove") {
      if (selectedRunId === runId) {
        setSelectedRunId(null);
        setSelectedRun(null);
      }
      setMessage(`Removed run #${runId}.`);
    } else {
      const payload = await response.json();
      const nextRun = payload.data as BoardImportRunDetail;
      setSelectedRunId(nextRun.id);
      setSelectedRun(nextRun);
      setMessage(action === "retry" ? `Queued retry run #${nextRun.id}.` : `Stopped run #${runId}.`);
    }
    await loadBoardsAndRuns();
  }

  async function runBulkAction(statusFilter: "done" | "failed") {
    setBulkAction(statusFilter);
    setError(null);
    setMessage(null);
    const response = await authFetch(`/api/v1/admin/board-imports/runs?status_filter=${statusFilter}`, {
      method: "DELETE",
    });
    setBulkAction(null);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? `Failed to clear ${statusFilter} runs.`);
      return;
    }
    const payload = await response.json();
    const deletedCount = Number(payload?.deleted_count ?? 0);
    setMessage(
      statusFilter === "done"
        ? `Cleared ${deletedCount} done runs.`
        : `Cleared ${deletedCount} failed/cancelled runs.`,
    );
    if (selectedRun && ((statusFilter === "done" && selectedRun.status === "done") || (statusFilter === "failed" && ["failed", "cancelled"].includes(selectedRun.status)))) {
      setSelectedRun(null);
      setSelectedRunId(null);
    }
    await loadBoardsAndRuns();
  }

  function canStop(run: BoardImportRun) {
    return ACTIVE_STATUSES.has(run.status);
  }

  function canRetry(run: BoardImportRun) {
    return !ACTIVE_STATUSES.has(run.status);
  }

  function canRemove(run: BoardImportRun) {
    return !ACTIVE_STATUSES.has(run.status);
  }

  function renderStatus(status: string) {
    const className =
      status === "done"
        ? "upload-status upload-status-ready"
        : status === "failed"
          ? "upload-status upload-status-failed"
          : "upload-status upload-status-queued";
    return <span className={className}>{status}</span>;
  }

  return (
    <AdminShell
      title="Board Importer"
      description="Pull posts from supported booru boards into NextBoo through the normal ingest pipeline."
    >
      {error ? <p className="form-error">{error}</p> : null}
      {message ? <p className="form-success">{message}</p> : null}

      <section className="panel">
        <h2>Queue Import</h2>
        {loading ? (
          <div className="empty-state">
            <strong>Loading board presets.</strong>
            <p>Fetching the importer catalog and recent runs.</p>
          </div>
        ) : (
          <form className="stack-form" onSubmit={handleSubmit}>
            <label>
              Source board
              <select disabled={allBoards} onChange={(event) => setBoardName(event.target.value)} value={boardName}>
                <option value="">Select board</option>
                {boards.map((board) => (
                  <option key={board.name} value={board.name}>
                    {board.name} ({board.family})
                  </option>
                ))}
              </select>
            </label>
            <label className="checkbox-row">
              <input checked={allBoards} onChange={(event) => setAllBoards(event.target.checked)} type="checkbox" />
              Queue to all available boards
            </label>
            <label>
              Tags
              <input
                onChange={(event) => setTags(event.target.value)}
                placeholder="1girl,solo,smile"
                type="text"
                value={tags}
              />
            </label>
            <label>
              Max posts this run
              <input
                min={1}
                max={250}
                onChange={(event) => setRequestedLimit(Math.max(Number.parseInt(event.target.value || "1", 10) || 1, 1))}
                type="number"
                value={requestedLimit}
              />
            </label>
            <div className="inline-form-note">
              <strong>Hourly budget:</strong> 1000 images per hour across all board imports.
            </div>
            <button className="primary-button" disabled={saving || (!allBoards && !boardName) || !tags.trim()} type="submit">
              {saving ? "Queueing..." : allBoards ? "Start all-board import" : "Start board import"}
            </button>
          </form>
        )}
      </section>

      <div className="two-column-grid board-import-grid">
        <section className="panel">
          <h2>Recent Runs</h2>
          <div className="board-import-actions board-import-bulk-actions">
            <button
              className="secondary-button"
              disabled={bulkAction !== null}
              onClick={() => void runBulkAction("done")}
              type="button"
            >
              Clear Done
            </button>
            <button
              className="secondary-button"
              disabled={bulkAction !== null}
              onClick={() => void runBulkAction("failed")}
              type="button"
            >
              Clear Failed
            </button>
          </div>
          <div className="table-wrap">
            <table className="simple-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Board</th>
                  <th>Status</th>
                  <th>Tags</th>
                  <th>Completed</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr
                    className={selectedRunId === run.id ? "board-import-row-selected" : undefined}
                    key={run.id}
                    onClick={() => setSelectedRunId(run.id)}
                  >
                    <td>{run.id}</td>
                    <td>{run.board_name}</td>
                    <td>{renderStatus(run.status)}</td>
                    <td>{run.tag_query}</td>
                    <td>{run.completed_posts}/{run.requested_limit}</td>
                    <td>
                      <div className="board-import-actions">
                        <button
                          aria-label={`Stop run ${run.id}`}
                          className="icon-button"
                          disabled={!canStop(run) || actionRunId === run.id}
                          onClick={(event) => {
                            event.stopPropagation();
                            void runAction(run.id, "stop");
                          }}
                          title="Stop"
                          type="button"
                        >
                          ■
                        </button>
                        <button
                          aria-label={`Retry run ${run.id}`}
                          className="icon-button"
                          disabled={!canRetry(run) || actionRunId === run.id}
                          onClick={(event) => {
                            event.stopPropagation();
                            void runAction(run.id, "retry");
                          }}
                          title="Retry"
                          type="button"
                        >
                          ↻
                        </button>
                        <button
                          aria-label={`Remove run ${run.id}`}
                          className="icon-button danger"
                          disabled={!canRemove(run) || actionRunId === run.id}
                          onClick={(event) => {
                            event.stopPropagation();
                            void runAction(run.id, "remove");
                          }}
                          title="Remove"
                          type="button"
                        >
                          ✕
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!runs.length ? (
                  <tr>
                    <td colSpan={6}>No board imports queued yet.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel">
          <h2>Run Detail</h2>
          {!selectedRun ? (
            <div className="empty-state">
              <strong>Select a run.</strong>
              <p>Choose a board import to inspect progress and logs.</p>
            </div>
          ) : (
            <div className="stack-form">
              <div className="board-import-stats">
                <div><strong>Board</strong><span>{selectedRun.board_name}</span></div>
                <div><strong>Status</strong><span>{selectedRun.status}</span></div>
                <div><strong>Requested</strong><span>{selectedRun.requested_limit}</span></div>
                <div><strong>Discovered</strong><span>{selectedRun.discovered_posts}</span></div>
                <div><strong>Downloaded</strong><span>{selectedRun.downloaded_posts}</span></div>
                <div><strong>Queued</strong><span>{selectedRun.queued_posts}</span></div>
                <div><strong>Completed</strong><span>{selectedRun.completed_posts}</span></div>
                <div><strong>Duplicates</strong><span>{selectedRun.duplicate_posts}</span></div>
                <div><strong>Failed</strong><span>{selectedRun.failed_posts}</span></div>
                <div><strong>Import Batch</strong><span>{selectedRun.source_import_batch_id ?? "none"}</span></div>
              </div>
              <div className="board-import-actions">
                <button
                  className="icon-button"
                  disabled={!canStop(selectedRun) || actionRunId === selectedRun.id}
                  onClick={() => void runAction(selectedRun.id, "stop")}
                  title="Stop"
                  type="button"
                >
                  ■
                </button>
                <button
                  className="icon-button"
                  disabled={!canRetry(selectedRun) || actionRunId === selectedRun.id}
                  onClick={() => void runAction(selectedRun.id, "retry")}
                  title="Retry"
                  type="button"
                >
                  ↻
                </button>
                <button
                  className="icon-button danger"
                  disabled={!canRemove(selectedRun) || actionRunId === selectedRun.id}
                  onClick={() => void runAction(selectedRun.id, "remove")}
                  title="Remove"
                  type="button"
                >
                  ✕
                </button>
              </div>
              {selectedRun.current_message ? (
                <div className="inline-form-note">
                  <strong>Current:</strong> {selectedRun.current_message}
                </div>
              ) : null}
              <div className="board-import-log">
                {selectedRun.events.map((event) => (
                  <article className={event.is_error ? "board-import-log-item error" : "board-import-log-item"} key={event.id}>
                    <div className="board-import-log-meta">
                      <span>{new Date(event.created_at).toLocaleString()}</span>
                      <span>{event.event_type}</span>
                      {event.remote_post_id ? <span>post {event.remote_post_id}</span> : null}
                      {event.job_id ? <span>job {event.job_id}</span> : null}
                      {event.image_id ? <span>image {event.image_id}</span> : null}
                    </div>
                    <div>{event.message}</div>
                  </article>
                ))}
                {!selectedRun.events.length ? (
                  <div className="empty-state">
                    <strong>No log entries yet.</strong>
                    <p>The runner has not written any events for this import.</p>
                  </div>
                ) : null}
              </div>
            </div>
          )}
        </section>
      </div>
    </AdminShell>
  );
}
