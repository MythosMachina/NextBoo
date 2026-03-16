"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AccountShell } from "../../components/account-shell";
import { authFetch, useAuthState } from "../../components/auth";

type BackupItem = {
  id: string;
  uuid_short: string;
  original_filename: string;
  created_at: string;
  rating: "general" | "sensitive" | "questionable" | "explicit";
  original_download_url: string | null;
};

type BackupExport = {
  id: number;
  status: "pending" | "running" | "done" | "failed";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  file_size: number | null;
  item_count: number;
  current_message: string | null;
  error_summary: string | null;
  download_url: string | null;
};

type BackupPayload = {
  data: BackupItem[];
  exports: BackupExport[];
  meta: {
    count: number;
    export_count: number;
    queued_export_id?: number;
    queued?: number;
  };
};

function humanFileSize(bytes: number | null): string {
  if (!bytes || bytes <= 0) {
    return "-";
  }
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(unit === 0 ? 0 : 2)} ${units[unit]}`;
}

export default function AccountBackupPage() {
  const router = useRouter();
  const { user, isTosDeactivated, loading: authLoading } = useAuthState();
  const [items, setItems] = useState<BackupItem[]>([]);
  const [exports, setExports] = useState<BackupExport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [creatingZip, setCreatingZip] = useState(false);

  async function loadBackup() {
    const response = await authFetch("/api/v1/users/me/backup");
    if (!response.ok) {
      setError("Failed to load your backup exports.");
      setLoading(false);
      return;
    }
    const payload = (await response.json()) as BackupPayload;
    setItems(payload.data);
    setExports(payload.exports ?? []);
    setLoading(false);
  }

  useEffect(() => {
    if (authLoading) {
      return;
    }
    if (!isTosDeactivated) {
      router.replace(user ? "/account" : "/login");
      return;
    }
    loadBackup();
  }, [authLoading, isTosDeactivated, router, user]);

  useEffect(() => {
    if (!isTosDeactivated) {
      return;
    }
    if (!exports.some((item) => item.status === "pending" || item.status === "running")) {
      return;
    }
    const timer = window.setInterval(() => {
      loadBackup();
    }, 4000);
    return () => window.clearInterval(timer);
  }, [exports]);

  async function startZipCreation() {
    setCreatingZip(true);
    setError(null);
    setMessage(null);
    const response = await authFetch("/api/v1/users/me/backup/exports", {
      method: "POST",
    });
    setCreatingZip(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setError(payload?.detail ?? "Failed to queue ZIP creation.");
      return;
    }
    const payload = (await response.json()) as BackupPayload;
    setItems(payload.data);
    setExports(payload.exports ?? []);
    setMessage(payload.meta?.queued ? "Zip creation started." : "A ZIP export is already being prepared.");
  }

  const deleteAfter = user?.tos_delete_after_at ? new Date(user.tos_delete_after_at) : null;
  const latestReadyExport = useMemo(
    () => exports.find((item) => item.status === "done" && item.download_url),
    [exports]
  );

  if (authLoading || !isTosDeactivated) {
    return null;
  }

  return (
    <AccountShell
      title="Backup Downloads"
      description="Your account is in backup-only mode. You can only request and download your own backup archives until the scheduled deletion date."
    >
      <section className="panel">
        <h2>Backup Window</h2>
        <div className="section-padding backup-summary">
          <p>
            Declining the Terms of Service placed this account into <strong>backup-only mode</strong>. Normal browsing, uploading, voting, commenting, and social interaction are disabled.
          </p>
          {deleteAfter ? <p><strong>Scheduled account deletion:</strong> {deleteAfter.toLocaleString()}</p> : null}
          <p><strong>Uploads available for backup:</strong> {items.length}</p>
        </div>
      </section>

      <section className="panel">
        <h2>ZIP Export</h2>
        <div className="section-padding backup-summary">
          <p>Request a full ZIP archive of your uploaded files. The archive is generated with low priority and will appear here once it is ready.</p>
          <div className="row-actions">
            <button className="primary-button" disabled={creatingZip || loading} onClick={startZipCreation} type="button">
              {creatingZip ? "Queuing..." : "Create Backup ZIP"}
            </button>
            {latestReadyExport?.download_url ? (
              <a className="secondary-button" href={latestReadyExport.download_url}>
                Download Latest ZIP
              </a>
            ) : null}
          </div>
          {message ? <p className="form-success">{message}</p> : null}
          {error ? <p className="form-error">{error}</p> : null}
        </div>
        {loading ? (
          <div className="empty-state">
            <strong>Loading backup exports.</strong>
            <p>Checking your current archive jobs.</p>
          </div>
        ) : exports.length ? (
          <div className="table-wrap">
            <table className="simple-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Status</th>
                  <th>Files</th>
                  <th>Size</th>
                  <th>Created</th>
                  <th>Message</th>
                  <th>Download</th>
                </tr>
              </thead>
              <tbody>
                {exports.map((item) => (
                  <tr key={item.id}>
                    <td>{item.id}</td>
                    <td>{item.status}</td>
                    <td>{item.item_count}</td>
                    <td>{humanFileSize(item.file_size)}</td>
                    <td>{new Date(item.created_at).toLocaleString()}</td>
                    <td>{item.current_message ?? item.error_summary ?? "-"}</td>
                    <td>
                      {item.download_url ? (
                        <a className="secondary-button" href={item.download_url}>
                          Download
                        </a>
                      ) : (
                        "-"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <strong>No ZIP export yet.</strong>
            <p>Start one above and this page will offer the archive once the low-priority job completes.</p>
          </div>
        )}
      </section>
    </AccountShell>
  );
}
