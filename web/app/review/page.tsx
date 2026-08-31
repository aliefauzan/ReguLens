"use client";

import { useEffect, useState } from "react";
import {
  confirmClause,
  dismissClause,
  listClauses,
  listDocuments,
  type Clause,
  type RegulatoryDocument,
} from "@/lib/api";
import Provenance from "../_ui/Provenance";
import Term from "../_ui/Term";
import { plain } from "../_ui/status";

// Why a clause waits here, said without the vocabulary of the pipeline.
const REASONS: Record<string, string> = {
  low_confidence: "We are not sure we read this correctly.",
  // Written by the guardrail as a single `review_reason`; without an entry here
  // the queue showed the rule with no explanation at all.
  low_confidence_or_flagged:
    "Either we are not sure we read this correctly, or the source is not official enough to act on by itself.",
  low_authority: "The source is not official enough to change anything on its own.",
  unnormalized_substance: "We do not recognise the ingredient name.",
  unnormalized_unit: "We do not recognise the unit of measurement.",
  non_numeric_clause: "This rule has no number in it, so it cannot be checked automatically.",
  ambiguous_relationship: "It is unclear whether this replaces an existing rule.",
};

/** Both shapes of "why is this here", in one list, never empty. */
function reasonsOf(clause: Clause): string[] {
  const listed = clause.review_reasons ?? [];
  if (listed.length > 0) return listed;
  if (clause.review_reason) return [clause.review_reason];
  return ["low_confidence_or_flagged"];
}

// Why a rule can be real, read correctly, and still not worth your time.
// Deliberately worded as "not applicable", never "not valid" — the app has no
// opinion on a regulation it cannot apply to anything you make.
const HELD_BACK: Record<string, string> = {
  no_market: "for countries you do not sell in",
  substance_absent: "about ingredients none of your products contain",
  product_type_absent: "about kinds of product you do not make",
};

export default function ReviewQueuePage() {
  const [clauses, setClauses] = useState<Clause[]>([]);
  const [documents, setDocuments] = useState<RegulatoryDocument[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  // Filtered by default. Watching whole regulations put two hundred entries in
  // here, almost all of them correct and none of them about anything in this
  // workspace — and a queue nobody reads hides the three that mattered.
  const [showAll, setShowAll] = useState(false);
  const [hidden, setHidden] = useState(0);
  const [hiddenReasons, setHiddenReasons] = useState<Record<string, number>>({});

  async function load(all = showAll) {
    try {
      const [clauseResult, documentResult] = await Promise.all([
        listClauses({ status: "needs_review", relevantOnly: !all }),
        listDocuments().catch(() => ({ documents: [] as RegulatoryDocument[] })),
      ]);
      setClauses(clauseResult.clauses);
      setHidden(clauseResult.hidden ?? 0);
      setHiddenReasons(clauseResult.hidden_reasons ?? {});
      setDocuments(documentResult.documents);
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

  async function toggleScope() {
    const next = !showAll;
    setShowAll(next);
    setLoading(true);
    await load(next);
  }

  async function confirm(id: string) {
    setBusy(id);
    try {
      await confirmClause(id);
      await load();
    } finally {
      setBusy(null);
    }
  }

  // Without this the queue only grew. A clause the reader judges wrong is
  // parked, not deleted — it keeps its record and its event, and nothing
  // evaluates against it again.
  async function dismiss(id: string) {
    setBusy(id);
    try {
      await dismissClause(id);
      await load();
    } finally {
      setBusy(null);
    }
  }

  const sourceById: Record<string, string> = Object.fromEntries(
    documents.map((doc) => [doc.id, doc.source_name]),
  );

  return (
    <main className="page page-mid" data-testid="review-page">
      <h1 className="t-large-title">Waiting for you to check</h1>
      <p className="t-body t-secondary prose-measure mt-2">
        ReguLens refused to act on these by itself — its{" "}
        <Term word="confidence">confidence</Term> was too low, or the source lacked the{" "}
        <Term word="authority">authority</Term>. Read each one. Accept it and it starts counting; ignore it and it is parked
        for good, though the record of it stays.
      </p>

      {!loading && !error && (hidden > 0 || showAll) ? (
        <div className="card mt-6 p-4" data-testid="review-scope">
          <p className="t-footnote t-secondary">
            {showAll ? (
              <>Showing every rule waiting to be checked, including ones that cannot affect anything you currently make.</>
            ) : (
              <>
                {hidden} more {hidden === 1 ? "rule is" : "rules are"} waiting but not shown —{" "}
                {Object.entries(hiddenReasons)
                  .map(([reason, count]) => `${count} ${HELD_BACK[reason] ?? plain(reason)}`)
                  .join(", ")}
                . They are kept, not discarded: add a product they apply to and they appear here.
              </>
            )}
          </p>
          <button
            className="btn btn-secondary btn-small mt-3"
            onClick={toggleScope}
            data-testid="toggle-review-scope"
          >
            {showAll ? "Only show what affects my products" : "Show them anyway"}
          </button>
        </div>
      ) : null}

      {loading ? <p className="t-body t-secondary mt-6">Loading…</p> : null}

      {error ? (
        <div className="card mt-6 p-5" data-testid="review-error">
          <p className="t-headline" style={{ color: "var(--danger)" }}>Service unavailable</p>
          <p className="t-footnote t-secondary mt-1">{error}</p>
        </div>
      ) : null}

      {!loading && !error && clauses.length === 0 ? (
        <div className="card mt-6 p-8 text-center" data-testid="review-empty">
          <p className="t-headline">Nothing to check</p>
          <p className="t-footnote t-secondary mt-1">
            {hidden > 0
              ? "Nothing here affects what you currently make. The rules we read are kept and will apply to any product you add."
              : "Every rule we read was clear enough to apply on its own."}
          </p>
        </div>
      ) : null}

      <ul className="mt-6 space-y-4">
        {clauses.map((clause) => (
          <li key={clause.id} className="card p-5" data-testid={`review-${clause.id}`}>
            <p className="t-body">{clause.text}</p>

            <ul className="mt-3 space-y-1">
              {reasonsOf(clause).map((reason) => (
                <li key={reason} className="t-footnote flex items-start gap-2" style={{ color: "var(--warn)" }}>
                  <span aria-hidden="true">•</span>
                  {REASONS[reason] ?? plain(reason)}
                </li>
              ))}
            </ul>

            <p className="t-footnote t-secondary mt-2">
              Read from {sourceById[clause.document_id] ?? "a document you added"}
              {typeof clause.confidence === "number"
                ? ` · we are ${Math.round(clause.confidence * 100)}% sure we read it correctly`
                : ""}
            </p>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <Provenance
                clauseId={clause.id}
                documentId={clause.document_id}
                sourceName={sourceById[clause.document_id]}
                jurisdiction={clause.jurisdiction}
              />
              <div className="flex flex-wrap gap-2">
                <button
                  className="btn btn-primary btn-small"
                  onClick={() => confirm(clause.id)}
                  disabled={busy === clause.id}
                  data-testid={`confirm-${clause.id}`}
                >
                  {busy === clause.id ? "Working…" : "This is correct — use it"}
                </button>
                <button
                  className="btn btn-secondary btn-small"
                  onClick={() => dismiss(clause.id)}
                  disabled={busy === clause.id}
                  data-testid={`dismiss-${clause.id}`}
                >
                  Not right — ignore it
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
