"use client";

import { FormEvent, useEffect, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type ImportBatch = {
  id: number;
  source_name: string;
  source_type?: string;
  status: string;
  total_files: number;
  processed_files: number;
  failed_files: number;
  created_at: string;
  updated_at: string;
};

type ImportSources = {
  folders: string[];
  zip_archives: string[];
};

export default function AdminImportsPage() {
  const [imports, setImports] = useState<ImportBatch[]>([]);
  const [sources, setSources] = useState<ImportSources>({ folders: [], zip_archives: [] });
  const [selectedFolder, setSelectedFolder] = useState("");
  const [selectedZip, setSelectedZip] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadData() {
    const [importsResponse, sourcesResponse] = await Promise.all([
      authFetch("/api/v1/jobs/imports"),
      authFetch("/api/v1/uploads/import-sources"),
    ]);

    if (!importsResponse.ok) {
      setError("Failed to load imports.");
      setLoading(false);
      return;
    }

    const importsPayload = await importsResponse.json();
    setImports(importsPayload.data);

    if (sourcesResponse.ok) {
      const sourcesPayload = await sourcesResponse.json();
      setSources(sourcesPayload.data);
      if (!selectedFolder && sourcesPayload.data.folders.length) {
        setSelectedFolder(sourcesPayload.data.folders[0]);
      }
      if (!selectedZip && sourcesPayload.data.zip_archives.length) {
        setSelectedZip(sourcesPayload.data.zip_archives[0]);
      }
    }

    setLoading(false);
  }

  useEffect(() => {
    loadData();
  }, []);

  async function submitFolderImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFolder) {
      setError("Choose a folder source first.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setMessage(null);
    const response = await authFetch("/api/v1/uploads/import-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_name: selectedFolder }),
    });
    setSubmitting(false);
    if (!response.ok) {
      setError("Failed to queue folder import.");
      return;
    }
    const payload = await response.json();
    setMessage(`Folder import queued: ${payload.meta.count} jobs, ${payload.meta.rejected_count} rejected.`);
    await loadData();
  }

  async function submitZipImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedZip) {
      setError("Choose a ZIP source first.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setMessage(null);
    const response = await authFetch("/api/v1/uploads/import-zip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ zip_name: selectedZip }),
    });
    setSubmitting(false);
    if (!response.ok) {
      setError("Failed to queue ZIP import.");
      return;
    }
    const payload = await response.json();
    setMessage(`ZIP import queued: ${payload.meta.count} jobs, ${payload.meta.rejected_count} rejected.`);
    await loadData();
  }

  return (
    <AdminShell title="Imports" description="Queue server-side folder or ZIP imports and review batch-level progress.">
      {error ? <p className="form-error">{error}</p> : null}
      {message ? <p className="form-success">{message}</p> : null}

      <section className="panel">
        <h2>Import Sources</h2>
        {loading ? (
          <div className="empty-state">
            <strong>Loading import sources.</strong>
            <p>Scanning the server import directory.</p>
          </div>
        ) : (
          <div className="two-column-grid">
            <form className="stack-form" onSubmit={submitFolderImport}>
              <h3>Folder Import</h3>
              <label>
                Server folder
                <select onChange={(event) => setSelectedFolder(event.target.value)} value={selectedFolder}>
                  <option value="">Select folder</option>
                  {sources.folders.map((folder) => (
                    <option key={folder} value={folder}>
                      {folder}
                    </option>
                  ))}
                </select>
              </label>
              <button className="primary-button" disabled={submitting || !selectedFolder} type="submit">
                {submitting ? "Queueing..." : "Queue folder import"}
              </button>
            </form>

            <form className="stack-form" onSubmit={submitZipImport}>
              <h3>ZIP Import</h3>
              <label>
                ZIP archive
                <select onChange={(event) => setSelectedZip(event.target.value)} value={selectedZip}>
                  <option value="">Select ZIP archive</option>
                  {sources.zip_archives.map((zipName) => (
                    <option key={zipName} value={zipName}>
                      {zipName}
                    </option>
                  ))}
                </select>
              </label>
              <button className="primary-button" disabled={submitting || !selectedZip} type="submit">
                {submitting ? "Queueing..." : "Queue ZIP import"}
              </button>
            </form>
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Import Batches</h2>
        <div className="table-wrap">
          <table className="simple-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Source</th>
                <th>Status</th>
                <th>Total</th>
                <th>Processed</th>
                <th>Failed</th>
              </tr>
            </thead>
            <tbody>
              {imports.map((item) => (
                <tr key={item.id}>
                  <td>{item.id}</td>
                  <td>{item.source_name}</td>
                  <td>{item.status}</td>
                  <td>{item.total_files}</td>
                  <td>{item.processed_files}</td>
                  <td>{item.failed_files}</td>
                </tr>
              ))}
              {!imports.length ? (
                <tr>
                  <td colSpan={6}>No import batches yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </AdminShell>
  );
}
