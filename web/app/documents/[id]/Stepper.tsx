"use client";

import { useCallback, useEffect, useState } from "react";
import { getDocument, retryDocument } from "@/lib/api";
import type { Clause, RegulatoryDocument } from "@/lib/api";

const POLL_MS = 2000;

const STAGES: { key: string; label: string }[] = [
  { key: "uploaded", label: "Uploaded" },
  { key: "extracting", label: "Extracting" },
  { key: "extracted", label: "Extracted" },
  { key: "reconciling", label: "Reconciling" },
  { key: "updated", label: "Updated" },
];

function stageIndex(status: string): number {
  switch (status) {
    case "uploaded":
      return 1;
    case "extracting":
      return 2;
    case "extracted":
      return 3;
    case "reconciled":
      return 5;
    default:
      return 1;
  }
}

function pct(value?: number): string {
  if (value === undefined || value === null) return "—";
  return Math.round(value * 100) + "%";
}

export default function Stepper({ documentId }: { documentId: string }) {
  const [doc, setDoc] = useState<RegulatoryDocument | null>(null);
  const [clauses, setClauses] = useState<Clause[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async function load() {
      try {
        const data = await getDocument(documentId);
        setDoc(data.document);
        setClauses(data.clauses);
        setError(null);
      } catch {
        setError("Could not reach the API.");
      }
    },
    [documentId],
  );

  useEffect(() => {
    load();
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  if (error !== null) {
    return (
      <p className="text-sm text-red-600" data-testid="doc-error">
        {error}
      </p>
    );
  }

  if (doc === null) {
    return <p className="text-sm opacity-60">Loading…</p>;
  }

  const failed = doc.status === "failed";
  const currentIndex = failed ? STAGES.length : stageIndex(doc.status);

  return (
    <div>
      <ol className="flex flex-wrap gap-2 text-sm" data-testid="pipeline-stepper">
        {STAGES.map((stage, index) => {
          const done = index + 1 < currentIndex;
          const active = !failed && index + 1 === currentIndex;
          return (
            <li
              key={stage.key}
              className={
                "rounded border px-3 py-1 " +
                (done ? "opacity-40 line-through " : "") +
                (active ? "border-black dark:border-white font-medium" : "opacity-60")
              }
              data-testid={"stage-" + stage.key}
            >
              {stage.label}
            </li>
          );
        })}
      </ol>

      {failed ? (
        <div className="mt-4 rounded border border-red-300 p-4" data-testid="failed-panel">
          <p className="text-sm text-red-600">{doc.error}</p>
          <button
            type="button"
            className="mt-2 rounded border px-3 py-1 text-sm"
            onClick={() => retryDocument(doc.id)}
            data-testid="retry-button"
          >
            Retry extraction
          </button>
        </div>
      ) : null}

      {clauses.length > 0 ? (
        <section className="mt-8" data-testid="clause-list">
          <h2 className="text-sm font-medium uppercase tracking-wide opacity-60">
            Extracted clauses ({clauses.length})
          </h2>
          <ul className="mt-3 space-y-3">
            {clauses.map((clause) => (
              <li key={clause.id} className="rounded border p-4 text-sm" data-testid={"clause-" + clause.id}>
                <p>{clause.text}</p>
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 opacity-80">
                  <span className="font-medium">{clause.substance ?? "—"}</span>
                  {clause.limit_value !== null && clause.limit_value !== undefined ? (
                    <span>
                      ≤ {String(clause.limit_value)} {clause.unit_raw ?? ""}
                    </span>
                  ) : null}
                  <span>{clause.clause_type}</span>
                  <span>{clause.product_type ?? "any product type"}</span>
                  {clause.effective_date ? <span>effective {clause.effective_date}</span> : null}
                  <span className="ml-auto group cursor-help relative" data-testid={"confidence-" + clause.id}>
                    confidence {pct(clause.confidence)}
                    <span
                      className="invisible absolute right-0 top-6 z-10 w-64 rounded border bg-white p-2 text-xs shadow-lg dark:bg-black group-hover:visible"
                      data-testid={"confidence-breakdown-" + clause.id}
                    >
                      parse quality {pct(clause.confidence_breakdown?.parse_quality)} · agreement{" "}
                      {pct(clause.confidence_breakdown?.self_consistency)} · source authority{" "}
                      {pct(clause.confidence_breakdown?.authority_tier)}
                    </span>
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
