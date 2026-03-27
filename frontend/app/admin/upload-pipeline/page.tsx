"use client";

import { useEffect, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type StageCard = {
  stage: string;
  label: string;
  workers: number;
  queued: number;
  running: number;
  failed: number;
  completed: number;
  total: number;
  media_images: number;
  media_videos: number;
  last_activity_at: string | null;
};

type LiveBatch = {
  id: number;
  submitted_by_username: string | null;
  status: string;
  total_items: number;
  completed_items: number;
  duplicate_items: number;
  rejected_items: number;
  failed_items: number;
  updated_at: string;
};

type ControlRoom = {
  stages: StageCard[];
  active_batches: LiveBatch[];
  worker_image_count: number;
  worker_video_count: number;
  queue_image_depth: number;
  queue_video_depth: number;
  quarantined_items: number;
  failed_items: number;
  duplicate_items: number;
  accepted_items: number;
  last_refresh_at: string;
};

type BalancerStage = {
  stage: string;
  label: string;
  min_workers: number;
  max_workers: number;
  jobs_per_worker: number;
  current_workers: number;
  recommended_workers: number;
  queue_depth: number;
  oldest_queued_seconds: number;
  score: number;
  active_workers: string[];
};

type BalancerSettings = {
  upload_pipeline_balancer_enabled: boolean;
  upload_pipeline_balancer_poll_seconds: number;
  upload_pipeline_balancer_flexible_slots: number;
  stages: BalancerStage[];
  last_rebalance_at: string | null;
  last_rebalance_summary: string | null;
  last_error: string | null;
};

const EMPTY_STATE: ControlRoom = {
  stages: [],
  active_batches: [],
  worker_image_count: 0,
  worker_video_count: 0,
  queue_image_depth: 0,
  queue_video_depth: 0,
  quarantined_items: 0,
  failed_items: 0,
  duplicate_items: 0,
  accepted_items: 0,
  last_refresh_at: "",
};

const EMPTY_BALANCER: BalancerSettings = {
  upload_pipeline_balancer_enabled: false,
  upload_pipeline_balancer_poll_seconds: 20,
  upload_pipeline_balancer_flexible_slots: 8,
  stages: [],
  last_rebalance_at: null,
  last_rebalance_summary: null,
  last_error: null,
};

function stageTone(stage: StageCard): string {
  if (stage.failed > 0) return "alarm";
  if (stage.running > 0) return "live";
  if (stage.queued > 0) return "warn";
  return "idle";
}

function operationalTone(runtime: BalancerStage | undefined, stage: StageCard): string {
  if (stage.failed > 0) return "alarm";
  if (runtime && runtime.queue_depth > 0 && runtime.recommended_workers > runtime.current_workers) return "scale";
  if (stage.running > 0) return "live";
  if (stage.queued > 0) return "warn";
  return "idle";
}

function statusLabel(runtime: BalancerStage | undefined, stage: StageCard): string {
  if (stage.failed > 0) return "Error";
  if (runtime && runtime.queue_depth > 0 && runtime.recommended_workers > runtime.current_workers) return "Backlog / Scaling";
  if (stage.running > 0) return "Running";
  if (stage.queued > 0) return "Queued";
  return "Idle";
}

export default function AdminUploadPipelinePage() {
  const [state, setState] = useState<ControlRoom>(EMPTY_STATE);
  const [balancer, setBalancer] = useState<BalancerSettings>(EMPTY_BALANCER);
  const [draft, setDraft] = useState<BalancerSettings>(EMPTY_BALANCER);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [acknowledgingFailed, setAcknowledgingFailed] = useState(false);
  const [acknowledgingFinalFailed, setAcknowledgingFinalFailed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [fieldDrafts, setFieldDrafts] = useState<Record<string, string>>({});
  const [editingField, setEditingField] = useState<string | null>(null);

  async function loadState(forceDraftRefresh = false) {
    const [controlRoomResponse, balancerResponse] = await Promise.all([
      authFetch("/api/v1/admin/upload-pipeline", { cache: "no-store" }),
      authFetch("/api/v1/admin/settings/upload-pipeline-balancer", { cache: "no-store" }),
    ]);
    if (!controlRoomResponse.ok || !balancerResponse.ok) {
      setError("Failed to load upload pipeline status.");
      setLoading(false);
      return;
    }
    const [controlRoomPayload, balancerPayload] = await Promise.all([
      controlRoomResponse.json(),
      balancerResponse.json(),
    ]);
    setState(controlRoomPayload.data);
    setBalancer(balancerPayload.data);
    if (forceDraftRefresh || !editingField) {
      setDraft(balancerPayload.data);
    }
    setLoading(false);
    setError(null);
  }

  useEffect(() => {
    loadState(true);
    const intervalId = window.setInterval(() => {
      loadState(false);
    }, 3000);
    return () => window.clearInterval(intervalId);
  }, [editingField]);

  function updateDraft<K extends keyof BalancerSettings>(key: K, value: BalancerSettings[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function updateStageValue(
    currentDraft: BalancerSettings,
    stageKey: string,
    field: "min_workers" | "max_workers" | "jobs_per_worker",
    value: number,
  ): BalancerSettings {
    return {
      ...currentDraft,
      stages: currentDraft.stages.map((stage) =>
        stage.stage === stageKey
          ? {
              ...stage,
              [field]: value,
            }
          : stage,
      ),
    };
  }

  async function persistDraft(nextDraft?: BalancerSettings) {
    const payloadDraft = nextDraft ?? draft;
    setSaving(true);
    setError(null);
    setMessage(null);
    const response = await authFetch("/api/v1/admin/settings/upload-pipeline-balancer", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        upload_pipeline_balancer_enabled: payloadDraft.upload_pipeline_balancer_enabled,
        upload_pipeline_balancer_poll_seconds: Math.max(payloadDraft.upload_pipeline_balancer_poll_seconds, 5),
        upload_pipeline_balancer_flexible_slots: Math.max(payloadDraft.upload_pipeline_balancer_flexible_slots, 0),
        stages: payloadDraft.stages.map((stage) => ({
          stage: stage.stage,
          min_workers: Math.max(stage.min_workers, 1),
          max_workers: Math.max(stage.max_workers, 1),
          jobs_per_worker: Math.max(stage.jobs_per_worker, 1),
        })),
      }),
    });
    setSaving(false);
    if (!response.ok) {
      setError("Failed to save upload pipeline balancer settings.");
      return;
    }
    const payload = await response.json();
    setBalancer(payload.data);
    setDraft(payload.data);
    setMessage("Upload pipeline stage settings saved.");
  }

  function fieldKey(stageKey: string, field: "min_workers" | "max_workers" | "jobs_per_worker"): string {
    return `${stageKey}:${field}`;
  }

  function beginStageEdit(stageKey: string, field: "min_workers" | "max_workers" | "jobs_per_worker", value: number) {
    const key = fieldKey(stageKey, field);
    setEditingField(key);
    setFieldDrafts((current) => ({ ...current, [key]: String(value) }));
  }

  function changeStageEdit(stageKey: string, field: "min_workers" | "max_workers" | "jobs_per_worker", value: string) {
    const key = fieldKey(stageKey, field);
    setFieldDrafts((current) => ({ ...current, [key]: value }));
  }

  async function commitStageEdit(stageKey: string, field: "min_workers" | "max_workers" | "jobs_per_worker", fallbackValue: number) {
    const key = fieldKey(stageKey, field);
    const rawValue = fieldDrafts[key];
    const parsed = Math.max(Number.parseInt(rawValue || String(fallbackValue), 10) || fallbackValue, 1);
    const nextDraft = updateStageValue(draft, stageKey, field, parsed);
    setDraft(nextDraft);
    setFieldDrafts((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
    setEditingField((current) => (current === key ? null : current));
    await persistDraft(nextDraft);
  }

  function cancelStageEdit(stageKey: string, field: "min_workers" | "max_workers" | "jobs_per_worker") {
    const key = fieldKey(stageKey, field);
    setFieldDrafts((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
    setEditingField((current) => (current === key ? null : current));
  }

  function stageInputValue(stage: BalancerStage, field: "min_workers" | "max_workers" | "jobs_per_worker"): string {
    const key = fieldKey(stage.stage, field);
    return fieldDrafts[key] ?? String(stage[field]);
  }

  async function acknowledgeFailed() {
    setAcknowledgingFailed(true);
    setError(null);
    setMessage(null);
    const response = await authFetch("/api/v1/admin/upload-pipeline/acknowledge-failed", {
      method: "POST",
    });
    setAcknowledgingFailed(false);
    if (!response.ok) {
      setError("Failed to acknowledge failed pipeline items.");
      return;
    }
    const payload = await response.json();
    setState(payload.data);
    setMessage(`Acknowledged ${payload.meta?.acknowledged_failed_items ?? 0} failed pipeline items.`);
  }

  async function acknowledgeFinalFailed() {
    setAcknowledgingFinalFailed(true);
    setError(null);
    setMessage(null);
    const response = await authFetch("/api/v1/admin/upload-pipeline/acknowledge-final-failed", {
      method: "POST",
    });
    setAcknowledgingFinalFailed(false);
    if (!response.ok) {
      setError("Failed to acknowledge failed final ingest jobs.");
      return;
    }
    const payload = await response.json();
    setState(payload.data);
    setMessage(`Acknowledged ${payload.meta?.acknowledged_final_failed_jobs ?? 0} failed final ingest jobs.`);
  }

  const activePressureStages = balancer.stages.filter((stage) => stage.queue_depth > 0 || stage.oldest_queued_seconds > 0);
  const stageRuntimeByKey = new Map(balancer.stages.map((stage) => [stage.stage, stage] as const));

  return (
    <AdminShell
      title="Upload Pipeline"
      description="Live control room for the staged upload ingress. Watch quarantine, scan, dedupe, normalize, dispatch, and final ingest in near realtime."
    >
      <section className="panel control-room-summary">
        <div className="control-room-legend">
          <span className="control-room-legend-item tone-live">Running</span>
          <span className="control-room-legend-item tone-idle">Idle</span>
          <span className="control-room-legend-item tone-alarm">Error</span>
          <span className="control-room-legend-item tone-scale">Backlog / Scaling</span>
        </div>
        <div className="control-room-kpis">
          <div className="control-room-kpi">
            <span>Quarantined</span>
            <strong>{state.quarantined_items}</strong>
          </div>
          <div className="control-room-kpi">
            <span>Accepted</span>
            <strong>{state.accepted_items}</strong>
          </div>
          <div className="control-room-kpi">
            <span>Duplicates</span>
            <strong>{state.duplicate_items}</strong>
          </div>
          <div className="control-room-kpi">
            <span>Failed</span>
            <strong>{state.failed_items}</strong>
          </div>
          <div className="control-room-kpi">
            <span>Image Queue</span>
            <strong>{state.queue_image_depth}</strong>
          </div>
          <div className="control-room-kpi">
            <span>Video Queue</span>
            <strong>{state.queue_video_depth}</strong>
          </div>
          <div className="control-room-kpi">
            <span>Pressed Stages</span>
            <strong>{activePressureStages.length}</strong>
          </div>
        </div>
        <div className="control-room-actions">
          <button
            className="secondary-button"
            disabled={acknowledgingFailed || state.failed_items === 0}
            onClick={() => void acknowledgeFailed()}
            type="button"
          >
            {acknowledgingFailed ? "Acknowledging..." : "Acknowledge Failed"}
          </button>
          <button
            className="secondary-button"
            disabled={acknowledgingFinalFailed || !state.stages.some((stage) => stage.stage === "final_ingest" && stage.failed > 0)}
            onClick={() => void acknowledgeFinalFailed()}
            type="button"
          >
            {acknowledgingFinalFailed ? "Acknowledging..." : "Acknowledge Final Failed"}
          </button>
        </div>
        <div className="inline-form-note">
          <strong>Live refresh:</strong> {state.last_refresh_at || "waiting"}
        </div>
        <div className="inline-form-note">
          <strong>Workers:</strong> image {state.worker_image_count} / video {state.worker_video_count}
        </div>
        <div className="inline-form-note">
          <strong>Last rebalance:</strong> {balancer.last_rebalance_summary ?? "none"} | {balancer.last_rebalance_at ?? "never"}
        </div>
        {balancer.last_error ? (
          <p className="form-error">Balancer error: {balancer.last_error}</p>
        ) : null}
      </section>

      <section className="panel">
        <h2>Process Line</h2>
        {loading ? (
          <div className="empty-state">
            <strong>Loading control room.</strong>
            <p>Collecting staged upload telemetry.</p>
          </div>
        ) : error ? (
          <p className="form-error">{error}</p>
        ) : (
          <div className="control-room-plant">
            <div className="control-room-flow-rail" />
            <div className="control-room-line">
              {state.stages.map((stage, index) => {
                const runtime = stageRuntimeByKey.get(stage.stage);
                const tone = operationalTone(runtime, stage);
                return (
                  <article className={`control-room-stage tone-${tone}`} key={stage.stage}>
                    <div className="control-room-node" aria-hidden="true" />
                    <header>
                      <div>
                        <p className="control-room-stage-label">{statusLabel(runtime, stage)}</p>
                        <h3>{stage.label}</h3>
                      </div>
                      <span className="control-room-pulse" />
                    </header>
                    <div className="control-room-stage-grid">
                      <div><span>Queued</span><strong>{stage.queued}</strong></div>
                      <div><span>Running</span><strong>{stage.running}</strong></div>
                      <div><span>Failed</span><strong>{stage.failed}</strong></div>
                      <div><span>Done</span><strong>{stage.completed}</strong></div>
                    </div>
                    <div className="control-room-stage-meta">
                      <span>Now {runtime?.current_workers ?? stage.workers}</span>
                      <span>Target {runtime?.recommended_workers ?? stage.workers}</span>
                      <span>Total {stage.total}</span>
                    </div>
                    <div className="control-room-stage-meta">
                      <span>Img {stage.media_images}</span>
                      <span>Vid {stage.media_videos}</span>
                      <span>Age {runtime?.oldest_queued_seconds ?? 0}s</span>
                    </div>
                    <div className="control-room-pressure-bar" aria-hidden="true">
                      <span
                        style={{
                          width: `${Math.min(
                            100,
                            Math.max(
                              stage.failed > 0
                                ? 100
                                : runtime
                                  ? runtime.queue_depth * 6 + runtime.score * 12
                                  : stage.queued * 8,
                              tone === "live" ? 18 : 6,
                            ),
                          )}%`,
                        }}
                      />
                    </div>
                    <small>Last activity: {stage.last_activity_at ?? "none"}</small>
                    {index < state.stages.length - 1 ? <div className="control-room-stage-link" aria-hidden="true" /> : null}
                  </article>
                );
              })}
            </div>
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Stage Allocation</h2>
        <div className="inline-form-note">
          <strong>Autosave:</strong> stage changes are applied automatically after you stop editing.
        </div>
        <div className="inline-form-note">
          <strong>Status:</strong> {saving ? "saving" : editingField ? "editing" : "saved"}
        </div>
        {message ? <p className="form-success">{message}</p> : null}
        {error ? <p className="form-error">{error}</p> : null}
        {loading ? (
          <div className="empty-state compact-empty-state">
            <strong>Loading stage allocation.</strong>
            <p>Waiting for balancer telemetry.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="simple-table">
              <thead>
                <tr>
                  <th>Stage</th>
                  <th>Current</th>
                  <th>Recommended</th>
                  <th>Min</th>
                  <th>Max</th>
                  <th>Jobs/Worker</th>
                  <th>Queued</th>
                  <th>Oldest</th>
                  <th>Score</th>
                  <th>Active Workers</th>
                </tr>
              </thead>
              <tbody>
                {draft.stages.map((stage) => {
                  const runtime = balancer.stages.find((item) => item.stage === stage.stage) ?? stage;
                  return (
                    <tr key={stage.stage}>
                      <td>{stage.label}</td>
                      <td>{runtime.current_workers}</td>
                      <td>{runtime.recommended_workers}</td>
                      <td>
                        <input
                          className="compact-inline-input"
                          min={1}
                          onBlur={() => void commitStageEdit(stage.stage, "min_workers", stage.min_workers)}
                          onChange={(event) => changeStageEdit(stage.stage, "min_workers", event.target.value)}
                          onFocus={() => beginStageEdit(stage.stage, "min_workers", stage.min_workers)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") {
                              event.preventDefault();
                              event.currentTarget.blur();
                            } else if (event.key === "Escape") {
                              cancelStageEdit(stage.stage, "min_workers");
                              event.currentTarget.blur();
                            }
                          }}
                          type="number"
                          value={stageInputValue(stage, "min_workers")}
                        />
                      </td>
                      <td>
                        <input
                          className="compact-inline-input"
                          min={1}
                          onBlur={() => void commitStageEdit(stage.stage, "max_workers", stage.max_workers)}
                          onChange={(event) => changeStageEdit(stage.stage, "max_workers", event.target.value)}
                          onFocus={() => beginStageEdit(stage.stage, "max_workers", stage.max_workers)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") {
                              event.preventDefault();
                              event.currentTarget.blur();
                            } else if (event.key === "Escape") {
                              cancelStageEdit(stage.stage, "max_workers");
                              event.currentTarget.blur();
                            }
                          }}
                          type="number"
                          value={stageInputValue(stage, "max_workers")}
                        />
                      </td>
                      <td>
                        <input
                          className="compact-inline-input"
                          min={1}
                          onBlur={() => void commitStageEdit(stage.stage, "jobs_per_worker", stage.jobs_per_worker)}
                          onChange={(event) => changeStageEdit(stage.stage, "jobs_per_worker", event.target.value)}
                          onFocus={() => beginStageEdit(stage.stage, "jobs_per_worker", stage.jobs_per_worker)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") {
                              event.preventDefault();
                              event.currentTarget.blur();
                            } else if (event.key === "Escape") {
                              cancelStageEdit(stage.stage, "jobs_per_worker");
                              event.currentTarget.blur();
                            }
                          }}
                          type="number"
                          value={stageInputValue(stage, "jobs_per_worker")}
                        />
                      </td>
                      <td>{runtime.queue_depth}</td>
                      <td>{runtime.oldest_queued_seconds}s</td>
                      <td>{runtime.score.toFixed(2)}</td>
                      <td className="compact-cell-list">
                        {runtime.active_workers.length ? runtime.active_workers.join(", ") : "none"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Active Batches</h2>
        {state.active_batches.length === 0 ? (
          <div className="empty-state compact-empty-state">
            <strong>No active staged batches.</strong>
            <p>The staged upload pipeline has not accepted batches yet.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="simple-table">
              <thead>
                <tr>
                  <th>Batch</th>
                  <th>User</th>
                  <th>Status</th>
                  <th>Total</th>
                  <th>Completed</th>
                  <th>Duplicate</th>
                  <th>Rejected</th>
                  <th>Failed</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {state.active_batches.map((batch) => (
                  <tr key={batch.id}>
                    <td>#{batch.id}</td>
                    <td>{batch.submitted_by_username ?? "unknown"}</td>
                    <td>{batch.status}</td>
                    <td>{batch.total_items}</td>
                    <td>{batch.completed_items}</td>
                    <td>{batch.duplicate_items}</td>
                    <td>{batch.rejected_items}</td>
                    <td>{batch.failed_items}</td>
                    <td>{batch.updated_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </AdminShell>
  );
}
