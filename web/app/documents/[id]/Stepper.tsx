"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { getDocument, retryDocument } from "@/lib/api";
import type { Clause, RegulatoryDocument } from "@/lib/api";
import { plain } from "../../_ui/status";

const POLL_MS = 2000;

// Measured on the deployed stack, upload to re-checked product: 183s. Saying
// "about a minute" and then taking three is how a working system gets read as
// a broken one, so both this and the upload button quote the same number.
const TYPICAL_SECONDS = 180;
const SLOW_SECONDS = 300;

// Stage names a first-time user can follow without knowing the pipeline.
const STAGES: { key: string; label: string; detail: string }[] = [
  { key: "uploaded", label: "Received", detail: "We have your document." },
  { key: "extracting", label: "Reading", detail: "Finding the rules and the numbers in them." },
  { key: "extracted", label: "Rules found", detail: "Each rule is listed below." },
  {
    key: "updated",
    label: "Compared and applied",
    detail: "Checked against the rules we already had, and any affected product re-checked.",
  },
];

/** How many stages are finished.
 *
 * The document's own status stops at `extracted`: reconciliation happens per
 * clause, on its own queue. So the last stage is derived from the clauses
 * themselves — while any of them is still `pending_reconciliation`, the work is
 * genuinely unfinished, and once none is, it genuinely is. A stepper that spins
 * forever on a finished job teaches people to distrust it. */
function completedStages(status: string, clauses: Clause[]): number {
  if (status === "uploaded") return 1;
  if (status === "extracting") return 2;
  if (status !== "extracted" && status !== "reconciled") return 1;

  const settled =
    clauses.length > 0 && clauses.every((c) => c.status !== "pending_reconciliation");
  return settled ? 4 : 3;
}

function pct(value?: number): string {
  if (value === undefined || value === null) return "—";
  return Math.round(value * 100) + "%";
}

function mmss(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function Stepper({ documentId }: { documentId: string }) {
  const [doc, setDoc] = useState<RegulatoryDocument | null>(null);
  const [clauses, setClauses] = useState<Clause[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Counted from when this page opened, not from upload: it is the only clock
  // the browser can honestly claim to have started.
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const load = useCallback(
    async function load() {
      try {
        const data = await getDocument(documentId);
        setDoc(data.document);
        setClauses(data.clauses);
        setError(null);
      } catch {
        setError("We could not reach the ReguLens service. Check that it is running, then reload this page.");
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
      <div className="card mt-8 p-5" data-testid="doc-error">
        <p className="t-headline" style={{ color: "var(--danger)" }}>Service unavailable</p>
        <p className="t-footnote t-secondary mt-1">{error}</p>
      </div>
    );
  }

  if (doc === null) {
    return <p className="t-body t-secondary mt-8">Loading…</p>;
  }

  const failed = doc.status === "failed";
  const complete = completedStages(doc.status, clauses);
  const done = !failed && complete >= STAGES.length;
  const working = !failed && !done;
  const slow = working && elapsed > SLOW_SECONDS;

  return (
    <div className="mt-8">
      {working ? (
        <div className="card mb-4 flex flex-wrap items-center justify-between gap-3 p-5" data-testid="wait-panel">
          <div>
            <p className="t-headline">
              {slow ? "This is taking longer than usual" : "Reading takes about three minutes"}
            </p>
            <p className="t-footnote t-secondary prose-measure mt-1">
              {slow
                ? "It has not failed — nothing times out silently. If it is still here in a few minutes, the document may be too long, and a shorter excerpt will read faster."
                : "Most of that is the model reading the document twice and the two reads being compared. Close this page if you like; it carries on without you."}
            </p>
          </div>
          <p
            className="t-number figure"
            style={{ color: slow ? "var(--warn)" : "var(--secondary)" }}
            data-testid="elapsed"
            aria-label={`${elapsed} seconds on this page`}
          >
            {mmss(elapsed)}
            <span className="figure-unit">of ~{mmss(TYPICAL_SECONDS)}</span>
          </p>
        </div>
      ) : null}

      <ol className="card overflow-hidden" data-testid="pipeline-stepper">
        {STAGES.map((stage, index) => {
          const finished = index < complete;
          const active = !failed && !done && index === complete;
          return (
            <li
              key={stage.key}
              className="row flex items-start gap-3 px-5 py-4"
              data-testid={"stage-" + stage.key}
            >
              <span
                aria-hidden="true"
                className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full t-caption"
                style={{
                  background: finished ? "var(--good)" : active ? "var(--accent)" : "var(--fill)",
                  color: finished || active ? "#fff" : "var(--secondary)",
                  fontWeight: 600,
                }}
              >
                {finished ? "✓" : index + 1}
              </span>
              <span>
                <span className="t-body block" style={{ fontWeight: active ? 600 : 400 }}>
                  {stage.label}
                  {active ? <span className="t-footnote t-secondary"> · working…</span> : null}
                </span>
                <span className="t-footnote t-secondary">{stage.detail}</span>
              </span>
            </li>
          );
        })}
      </ol>

      {done ? (
        <div className="card mt-4 p-5" style={{ borderLeft: "4px solid var(--good)" }}>
          <p className="t-headline">Finished</p>
          <p className="t-footnote t-secondary mt-1">
            Your products have been re-checked against these rules.
          </p>
          <Link href="/" className="btn btn-secondary btn-small mt-3">See your products</Link>
        </div>
      ) : null}

      {failed ? (
        <div className="card mt-4 p-5" style={{ borderLeft: "4px solid var(--danger)" }} data-testid="failed-panel">
          <p className="t-headline" style={{ color: "var(--danger)" }}>We could not read this document</p>
          <p className="t-footnote t-secondary mt-1">
            {doc.error ?? "Something went wrong while reading it."}
          </p>
          <p className="t-footnote t-secondary mt-2">
            The most common cause is a scanned PDF with no real text in it. Try pasting the text instead.
          </p>
          <button
            type="button"
            className="btn btn-secondary btn-small mt-3"
            onClick={() => retryDocument(doc.id)}
            data-testid="retry-button"
          >
            Try again
          </button>
        </div>
      ) : null}

      {clauses.length > 0 ? (
        <section className="mt-8" data-testid="clause-list">
          <h2 className="t-section">Rules found in this document ({clauses.length})</h2>
          <ul className="mt-3 space-y-3">
            {clauses.map((clause) => (
              <li key={clause.id} className="card p-5" data-testid={"clause-" + clause.id}>
                <p className="t-body">{clause.text}</p>

                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  <Fact label="Substance" value={clause.substance ?? "—"} />
                  <Fact
                    label="Maximum allowed"
                    value={
                      clause.limit_value !== null && clause.limit_value !== undefined
                        ? `${clause.limit_value} ${clause.unit_raw ?? ""}`
                        : "no number in this rule"
                    }
                  />
                  <Fact label="Applies to" value={plain(clause.product_type) || "any product"} />
                </div>

                <details className="mt-4">
                  <summary
                    className="t-footnote t-secondary cursor-pointer"
                    data-testid={"confidence-" + clause.id}
                  >
                    How sure are we? {pct(clause.confidence)}
                  </summary>
                  <div className="inset mt-2 p-4 t-footnote" data-testid={"confidence-breakdown-" + clause.id}>
                    <p>Text was clean and readable: {pct(clause.confidence_breakdown?.parse_quality)}</p>
                    <p className="mt-1">Two independent reads agreed: {pct(clause.confidence_breakdown?.self_consistency)}</p>
                    <p className="mt-1">Source is authoritative: {pct(clause.confidence_breakdown?.authority_tier)}</p>
                    {clause.needs_review ? (
                      <p className="mt-2" style={{ color: "var(--warn)" }}>
                        Below the bar to apply automatically — it is waiting for you under “To check”.
                      </p>
                    ) : null}
                  </div>
                </details>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="t-footnote t-secondary">{label}</p>
      <p className="t-body mt-1" style={{ fontWeight: 600 }}>{value}</p>
    </div>
  );
}
