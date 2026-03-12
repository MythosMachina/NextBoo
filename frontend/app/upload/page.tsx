"use client";

import { FormEvent, useEffect, useState } from "react";
import { authFetch, useAuthState } from "../components/auth";

type AcceptedUploadItem = {
  client_key: string;
  filename: string;
  job_id: number;
};

type RejectedUploadItem = {
  client_key: string;
  filename: string;
  error: string;
};

type UploadEntry = {
  clientKey: string;
  filename: string;
  filesize: number;
  jobId: number | null;
  status: "selected" | "uploading" | "queued" | "processing" | "ready" | "failed";
  detail: string;
};

export default function UploadPage() {
  const { authenticated, canUpload } = useAuthState();
  const [files, setFiles] = useState<FileList | null>(null);
  const [entries, setEntries] = useState<UploadEntry[]>([]);
  const [batchSummary, setBatchSummary] = useState<{ total: number; ready: number; failed: number; active: number }>({
    total: 0,
    ready: 0,
    failed: 0,
    active: 0
  });
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  if (!authenticated) {
    return (
      <section className="panel">
        <h2>Upload</h2>
        <div className="empty-state">
          <strong>Login required.</strong>
          <p>Guests cannot upload content.</p>
        </div>
      </section>
    );
  }

  if (!canUpload) {
    return (
      <section className="panel">
        <h2>Upload</h2>
        <div className="empty-state">
          <strong>Upload access not granted.</strong>
          <p>Request upload permission in your account settings.</p>
        </div>
      </section>
    );
  }

  useEffect(() => {
    const trackedIds = entries.map((entry) => entry.jobId).filter(Boolean) as number[];
    if (!trackedIds.length) {
      return;
    }
    const hasActiveEntries = entries.some((entry) => entry.status === "queued" || entry.status === "processing" || entry.status === "uploading");
    if (!hasActiveEntries) {
      return;
    }

    const intervalId = window.setInterval(async () => {
      const response = await authFetch(`/api/v1/uploads/status?job_ids=${trackedIds.join(",")}`);
      if (!response.ok) {
        return;
      }
      const payload = await response.json();
      const statusMap = new Map<number, { status: string; last_error: string | null }>();
      payload.data.forEach((item: { job_id: number; status: string; last_error: string | null }) => {
        statusMap.set(item.job_id, { status: item.status, last_error: item.last_error });
      });

      setEntries((current) =>
        current.map((entry) => {
          if (!entry.jobId) {
            return entry;
          }
          const update = statusMap.get(entry.jobId);
          if (!update) {
            return entry;
          }
          if (update.status === "done") {
            return { ...entry, status: "ready", detail: "Processed successfully" };
          }
          if (update.status === "failed") {
            return { ...entry, status: "failed", detail: update.last_error ?? "Processing failed" };
          }
          if (update.status === "queued") {
            return { ...entry, status: "queued", detail: "Waiting for worker" };
          }
          return { ...entry, status: "processing", detail: "Processing image" };
        })
      );
    }, 2500);

    return () => window.clearInterval(intervalId);
  }, [entries]);

  useEffect(() => {
    setBatchSummary({
      total: entries.length,
      ready: entries.filter((entry) => entry.status === "ready").length,
      failed: entries.filter((entry) => entry.status === "failed").length,
      active: entries.filter((entry) => entry.status === "uploading" || entry.status === "queued" || entry.status === "processing").length
    });
  }, [entries]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!files?.length) {
      setError("Select at least one file.");
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    setError(null);
    const allFiles = Array.from(files);
    const selectedEntries = allFiles.map((file, index) => ({
      clientKey: buildClientKey(file, index),
      filename: file.name,
      filesize: file.size,
      jobId: null,
      status: "uploading" as const,
      detail: "Uploading to server"
    }));
    setEntries(selectedEntries);
    const chunkSize = 50;
    const chunks = chunkFiles(allFiles, chunkSize);

    try {
      for (let batchIndex = 0; batchIndex < chunks.length; batchIndex += 1) {
        const chunk = chunks[batchIndex];
        const chunkKeys = new Set(chunk.map(({ clientKey }) => clientKey));
        setUploadProgress(Math.round((batchIndex / chunks.length) * 100));
        setEntries((current) =>
          current.map((entry) =>
            chunkKeys.has(entry.clientKey)
              ? { ...entry, status: "uploading", detail: `Uploading batch ${batchIndex + 1}/${chunks.length}` }
              : entry
          )
        );

        const payload = await uploadChunk(chunk);

        const acceptedMap = new Map(payload.data.map((item) => [item.client_key, item]));
        const rejectedMap = new Map(payload.rejected.map((item) => [item.client_key, item]));

        setEntries((current) =>
          current.map((entry) => {
            const isChunkEntry = chunkKeys.has(entry.clientKey);
            if (!isChunkEntry) {
              return entry;
            }
            const accepted = acceptedMap.get(entry.clientKey);
            if (accepted) {
              return {
                ...entry,
                jobId: accepted.job_id,
                status: "queued",
                detail: "Queued for processing"
              };
            }
            const rejected = rejectedMap.get(entry.clientKey);
            if (rejected) {
              return {
                ...entry,
                status: "failed",
                detail: rejected.error
              };
            }
            return {
              ...entry,
              status: "failed",
              detail: "Upload rejected"
            };
          })
        );
      }

      setUploadProgress(100);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Upload failed.");
      setEntries((current) =>
        current.map((entry) =>
          entry.status === "uploading"
            ? { ...entry, status: "failed", detail: "Upload failed" }
            : entry
        )
      );
    } finally {
      setUploading(false);
    }
  }

  function formatSize(bytes: number): string {
    if (bytes >= 1024 * 1024) {
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
    if (bytes >= 1024) {
      return `${Math.round(bytes / 1024)} KB`;
    }
    return `${bytes} B`;
  }

  return (
    <>
      <section className="form-panel panel">
        <h2>Upload</h2>
        <form className="stack-form" onSubmit={handleSubmit}>
          <label>
            Files
            <input
              multiple
              onChange={(event) => {
                setFiles(event.target.files);
                setEntries(
                  Array.from(event.target.files ?? []).map((file, index) => ({
                    clientKey: buildClientKey(file, index),
                    filename: file.name,
                    filesize: file.size,
                    jobId: null,
                    status: "selected",
                    detail: "Ready to upload"
                  }))
                );
              }}
              type="file"
            />
          </label>
          <button className="primary-button" disabled={uploading} type="submit">
            {uploading ? `Uploading... ${uploadProgress}%` : "Start upload"}
          </button>
          {error ? <p className="form-error">{error}</p> : null}
        </form>
      </section>

      <section className="panel">
        <h2>Bulk Upload Status</h2>
        {entries.length ? (
          <>
            <div className="upload-summary">
              <div><strong>{batchSummary.total}</strong><span>files</span></div>
              <div><strong>{batchSummary.ready}</strong><span>ready</span></div>
              <div><strong>{batchSummary.active}</strong><span>active</span></div>
              <div><strong>{batchSummary.failed}</strong><span>failed</span></div>
            </div>
            <div className="upload-list">
              {entries.map((entry) => (
                <article className="upload-item" key={entry.clientKey}>
                  <div className="upload-item-main">
                    <strong>{entry.filename}</strong>
                    <span>{formatSize(entry.filesize)}</span>
                  </div>
                  <div className="upload-item-status-row">
                    <span className={`upload-status upload-status-${entry.status}`}>{entry.status}</span>
                    <span>{entry.detail}</span>
                  </div>
                </article>
              ))}
            </div>
          </>
        ) : (
          <div className="empty-state">
            <strong>No files selected.</strong>
            <p>Select multiple images to start a bulk upload with live processing status.</p>
          </div>
        )}
      </section>
    </>
  );
}

function chunkFiles(files: File[], size: number): Array<Array<{ clientKey: string; file: File }>> {
  const chunks: Array<Array<{ clientKey: string; file: File }>> = [];
  for (let index = 0; index < files.length; index += size) {
    chunks.push(
      files.slice(index, index + size).map((file, offset) => ({
        clientKey: buildClientKey(file, index + offset),
        file
      }))
    );
  }
  return chunks;
}

async function uploadChunk(
  items: Array<{ clientKey: string; file: File }>
): Promise<{ data: AcceptedUploadItem[]; rejected: RejectedUploadItem[] }> {
  const formData = new FormData();
  items.forEach(({ clientKey, file }) => {
    formData.append("files", file);
    formData.append("client_keys", clientKey);
  });

  const response = await authFetch("/api/v1/uploads", {
    method: "POST",
    body: formData
  });

  if (!response.ok) {
    throw new Error(`Upload failed (${response.status}).`);
  }

  return (await response.json()) as { data: AcceptedUploadItem[]; rejected: RejectedUploadItem[] };
}

function buildClientKey(file: File, index = 0): string {
  return `${file.name}::${file.size}::${file.lastModified}::${index}`;
}
