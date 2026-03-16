"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getBrowserApiBaseUrl } from "../lib/public-api";

type TermsOfService = {
  title: string;
  version: string;
  paragraphs: string[];
  updated_at: string | null;
};

export default function TermsOfServicePage() {
  const [terms, setTerms] = useState<TermsOfService | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadTerms() {
      const response = await fetch(`${getBrowserApiBaseUrl()}/api/v1/invites/tos`, { cache: "no-store" });
      if (!response.ok) {
        setError("Failed to load the Terms of Service.");
        return;
      }
      const payload = await response.json();
      setTerms(payload.data);
    }

    loadTerms();
  }, []);

  return (
    <section className="panel tos-panel">
      <div className="tos-header">
        <div>
          <h2>{terms?.title ?? "Terms of Service"}</h2>
          <p>Review the current Terms of Service before redeeming an invite.</p>
        </div>
        <Link className="secondary-button" href="/invite">
          Back to Invite
        </Link>
      </div>
      {error ? <p className="form-error section-padding">{error}</p> : null}
      {!terms && !error ? (
        <div className="empty-state">
          <strong>Loading terms.</strong>
          <p>Fetching the latest published text.</p>
        </div>
      ) : null}
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
        </div>
      ) : null}
    </section>
  );
}
