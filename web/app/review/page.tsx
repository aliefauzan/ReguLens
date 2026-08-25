"use client";

import { useEffect, useState } from "react";
import { confirmClause, listClauses, type Clause } from "@/lib/api";
import { plain } from "../_ui/status";

// Why a clause waits here, said without the vocabulary of the pipeline.
const REASONS: Record<string, string> = {
  low_confidence: "We are not sure we read this correctly.",
  low_authority: "The source is not official enough to change anything on its own.",
  unnormalized_substance: "We do not recognise the ingredient name.",
  unnormalized_unit: "We do not recognise the unit of measurement.",
  non_numeric_clause: "This rule has no number in it, so it cannot be checked automatically.",
  ambiguous_relationship: "It is unclear whether this replaces an existing rule.",
};

export default function ReviewQueuePage() {
  const [clauses, setClauses] = useState<Clause[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    try {
      setClauses((await listClauses({ status: "needs_review" })).clauses);
      setError(null);
    } catch {
      setError("We could not reach the ReguLens service. Check that it is running, then reload this page.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function confirm(id: string) {
    setBusy(id);
    try {
      await confirmClause(id);
      await load();
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-5 py-8 sm:px-6 sm:py-12" data-testid="review-page">
      <h1 className="t-large-title">Waiting for you to check</h1>
      <p className="t-body t-secondary prose-measure mt-2">
        ReguLens refused to act on these by itself — it was not confident enough, or the source was not
        official enough. Read each one. If it is right, accept it and it starts counting.
      </p>

      {loading ? <p className="t-body t-secondary mt-8">Loading…</p> : null}

      {error ? (
        <div className="card mt-8 p-5" data-testid="review-error">
          <p className="t-headline" style={{ color: "var(--danger)" }}>Service unavailable</p>
          <p className="t-footnote t-secondary mt-1">{error}</p>
        </div>
      ) : null}

      {!loading && !error && clauses.length === 0 ? (
        <div className="card mt-8 p-8 text-center" data-testid="review-empty">
          <p className="t-headline">Nothing to check</p>
          <p className="t-footnote t-secondary mt-1">Every rule we read was clear enough to apply on its own.</p>
        </div>
      ) : null}

      <ul className="mt-8 space-y-4">
        {clauses.map((clause) => (
          <li key={clause.id} className="card p-5" data-testid={`review-${clause.id}`}>
            <p className="t-body">{clause.text}</p>

            <ul className="mt-3 space-y-1">
              {clause.review_reasons?.map((reason) => (
                <li key={reason} className="t-footnote flex items-start gap-2" style={{ color: "var(--warn)" }}>
                  <span aria-hidden="true">•</span>
                  {REASONS[reason] ?? plain(reason)}
                </li>
              ))}
            </ul>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <details>
                <summary className="t-caption cursor-pointer">Where this came from</summary>
                <p className="t-caption mono mt-1">{clause.id}</p>
              </details>
              <button
                className="btn btn-primary btn-small"
                onClick={() => confirm(clause.id)}
                disabled={busy === clause.id}
                data-testid={`confirm-${clause.id}`}
              >
                {busy === clause.id ? "Accepting…" : "This is correct — use it"}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
