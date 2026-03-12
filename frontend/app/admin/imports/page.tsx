"use client";

import { useEffect, useMemo, useState } from "react";
import { AdminShell } from "../../components/admin-shell";
import { authFetch } from "../../components/auth";

type ImportBatch = {
  id: number;
  source_name: string;
  status: string;
  total_files: number;
  processed_files: number;
  failed_files: number;
  created_at: string;
  updated_at: string;
};

export default function AdminImportsPage() {
  const [imports, setImports] = useState<ImportBatch[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      const response = await authFetch("/api/v1/jobs/imports");
      if (!response.ok) {
        setError("Failed to load imports.");
        return;
      }
      const payload = await response.json();
      setImports(payload.data);
    }

    loadData();
  }, []);

  return (
    <AdminShell title="Imports" description="Batch-level visibility into queued and completed imports.">
      {error ? <p className="form-error">{error}</p> : null}
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
            </tbody>
          </table>
        </div>
      </section>
    </AdminShell>
  );
}
