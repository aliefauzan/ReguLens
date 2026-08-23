"use client";

import { useEffect, useState } from "react";
import { confirmClause, listClauses, type Clause } from "@/lib/api";

export default function ReviewQueuePage() {
  const [clauses, setClauses] = useState<Clause[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      setClauses((await listClauses({ status: "needs_review" })).clauses);
      setError(null);
    } catch {
      setError("Could not reach the API.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function confirm(id: string) {
    await confirmClause(id);
    await load();
  }

  return (
    <main className="mx-auto max-w-5xl p-10" data-testid="review-page">
      <h1 className="text-2xl font-semibold tracking-tight">Review queue</h1>
      <p className="mt-1 text-sm opacity-70">
        Clauses the system refused to apply on its own. Confirming promotes a clause to active.
      </p>

      {loading ? <p className="mt-8 text-sm opacity-60">Loading…</p> : null}
      {error ? (
        <p className="mt-8 text-sm" style={{ color: "var(--danger)" }} data-testid="review-error">{error}</p>
      ) : null}

      {!loading && !error && clauses.length === 0 ? (
        <div className="card mt-8 p-8 text-center text-sm opacity-70" data-testid="review-empty">
          Nothing waiting for review.
        </div>
      ) : null}

      <ul className="mt-8 space-y-3">
        {clauses.map((clause) => (
          <li key={clause.id} className="card p-4 text-sm" data-testid={`review-${clause.id}`}>
            <div className="flex items-baseline justify-between gap-4">
              <span>{clause.text}</span>
              <button
                className="rounded-full border px-3 py-1 text-xs"
                onClick={() => confirm(clause.id)}
                data-testid={`confirm-${clause.id}`}
              >
                Confirm
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs opacity-70">
              <span className="font-mono">{clause.id}</span>
              {clause.review_reasons?.map((reason) => (
                <span key={reason} className="rounded-full px-2 py-0.5"
                  style={{ background: "var(--warn-soft)", color: "var(--warn)" }}>
                  {reason}
                </span>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
