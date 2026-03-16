"use client";

import { useEffect, useState } from "react";
import { authFetch, storeUser, useAuthState } from "../../components/auth";
import { getBrowserApiBaseUrl } from "../../lib/public-api";

type TermsOfService = {
  title: string;
  version: string;
  paragraphs: string[];
  updated_at: string | null;
};

export default function TermsOfServiceReviewPage() {
  const { setSession } = useAuthState();
  const [terms, setTerms] = useState<TermsOfService | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadTerms() {
      const response = await fetch(`${getBrowserApiBaseUrl()}/api/v1/invites/tos`, { cache: "no-store" });
      const payload = await response.json().catch(() => null);
      if (!response.ok || !payload?.data) {
        setError("Failed to load the Terms of Service.");
        return;
      }
      setTerms(payload.data);
    }

    loadTerms();
  }, []);

  async function acceptTerms() {
    setLoading(true);
    setError(null);
    const response = await authFetch("/api/v1/auth/tos/accept", { method: "POST" });
    const payload = await response.json().catch(() => null);
    setLoading(false);
    if (!response.ok || !payload?.data) {
      setError(payload?.detail ?? "Failed to accept the Terms of Service.");
      return;
    }
    storeUser(payload.data);
    setSession(payload.data);
    window.location.href = payload.data.role === "admin" || payload.data.role === "moderator" ? "/admin" : "/account";
  }

  async function declineTerms() {
    const confirmed = window.confirm(
      "If you decline the Terms of Service, your account will enter backup-only mode. You will lose normal site access immediately and the account will be deleted after 14 days. Continue?"
    );
    if (!confirmed) {
      return;
    }
    setLoading(true);
    setError(null);
    const response = await authFetch("/api/v1/auth/tos/decline", { method: "POST" });
    const payload = await response.json().catch(() => null);
    setLoading(false);
    if (!response.ok || !payload?.data) {
      setError(payload?.detail ?? "Failed to decline the Terms of Service.");
      return;
    }
    storeUser(payload.data);
    setSession(payload.data);
    window.location.href = "/account/backup";
  }

  return (
    <section className="panel tos-panel">
      <div className="tos-header">
        <div>
          <h2>{terms?.title ?? "Terms of Service Review"}</h2>
          <p>The Terms of Service changed. You must review the current version before continuing.</p>
        </div>
      </div>
      {error ? <p className="form-error section-padding">{error}</p> : null}
      {terms ? (
        <div className="tos-content section-padding">
          <div className="tos-meta">
            <span>Version {terms.version}</span>
            {terms.updated_at ? <span>Updated {new Date(terms.updated_at).toLocaleString()}</span> : null}
          </div>
          <div className="tos-blocks">
            {terms.paragraphs.map((paragraph, index) => (
              <article className="tos-block" key={`${terms.version}-${index}`}>
                <span className="tos-block-index">{index + 1}</span>
                <p>{paragraph}</p>
              </article>
            ))}
          </div>
          <div className="tos-review-actions">
            <button className="primary-button" disabled={loading} onClick={acceptTerms} type="button">
              {loading ? "Working..." : "Accept"}
            </button>
            <button className="danger-button compact-danger" disabled={loading} onClick={declineTerms} type="button">
              Decline
            </button>
          </div>
        </div>
      ) : (
        <div className="empty-state">
          <strong>Loading terms.</strong>
          <p>Fetching the latest published text.</p>
        </div>
      )}
    </section>
  );
}
