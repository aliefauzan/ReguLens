import Link from "next/link";
import { listClauses, listDocuments, type Clause } from "@/lib/api";
import Term from "../_ui/Term";
import { jurisdictionName, plain } from "../_ui/status";

export const dynamic = "force-dynamic";

/**
 * Everything ReguLens currently knows, in one list.
 *
 * Until now a clause was only visible inside the document that produced it, so
 * "what is this actually checking against?" had no answer short of opening
 * every upload in turn. A user cannot trust a verdict whose inputs they cannot
 * see.
 */
const STATUS_COPY: Record<string, { label: string; tone: string; meaning: string }> = {
  active: { label: "In use", tone: "var(--good)", meaning: "Counted in every check." },
  needs_review: {
    label: "Waiting for you",
    tone: "var(--warn)",
    meaning: "Not counted until you accept it.",
  },
  superseded: {
    label: "Replaced",
    tone: "var(--secondary)",
    meaning: "A newer rule from the same country took over.",
  },
  conflicted: {
    label: "Disagrees with another",
    tone: "var(--danger)",
    meaning:
      "Another country gives a different number for the same thing. This one still applies where it was issued, so it is counted.",
  },
  dismissed: {
    label: "Ignored",
    tone: "var(--secondary)",
    meaning: "You judged this one wrong. It never counts.",
  },
  pending_reconciliation: {
    label: "Still being sorted",
    tone: "var(--secondary)",
    meaning: "Read, but not yet compared with what we had.",
  },
};

export default async function RulesPage() {
  let clauses: Clause[] = [];
  let sourceById: Record<string, string> = {};
  let error: string | null = null;
  try {
    const [clauseResult, documentResult] = await Promise.all([listClauses({}), listDocuments()]);
    clauses = clauseResult.clauses;
    sourceById = Object.fromEntries(documentResult.documents.map((d) => [d.id, d.source_name]));
  } catch {
    error = "We could not reach the ReguLens service. Check that it is running, then reload this page.";
  }

  // `conflicted` still counts — a clause that disagrees with another country's
  // is enforced in its own jurisdiction, and it was the EU 150 mg/kg clause in
  // exactly that state that failed the demo product. Calling it "not counted"
  // would contradict the verdict on the next page.
  const COUNTED = new Set(["active", "conflicted"]);
  const inUse = clauses.filter((c) => COUNTED.has(c.status)).length;
  const ordered = [...clauses].sort((a, b) => {
    const rank = (c: Clause) => (c.status === "active" ? 0 : c.status === "needs_review" ? 1 : 2);
    return rank(a) - rank(b) || (a.jurisdiction ?? "").localeCompare(b.jurisdiction ?? "");
  });

  return (
    <main className="mx-auto max-w-5xl px-5 py-8 sm:px-6 sm:py-12" data-testid="rules-page">
      <h1 className="t-large-title">What ReguLens knows</h1>
      <p className="t-body t-secondary prose-measure mt-2">
        Every rule pulled out of the documents you added. {inUse} of {clauses.length}{" "}
        {clauses.length === 1 ? "is" : "are"} counted in your products&rsquo; verdicts right now —
        the rest say why they are not.
      </p>

      {error ? (
        <div className="card mt-8 p-5" data-testid="rules-error">
          <p className="t-headline" style={{ color: "var(--danger)" }}>Service unavailable</p>
          <p className="t-footnote t-secondary mt-1">{error}</p>
        </div>
      ) : null}

      {!error && clauses.length === 0 ? (
        <div className="card mt-8 p-8 text-center" data-testid="rules-empty">
          <p className="t-headline">No rules yet</p>
          <p className="t-footnote t-secondary mt-1">
            Add a regulation and everything read out of it appears here.
          </p>
          <Link href="/documents/new" className="btn btn-primary btn-small mt-4">Add rules</Link>
        </div>
      ) : null}

      <ul className="mt-8 space-y-3">
        {ordered.map((clause) => {
          const status = STATUS_COPY[clause.status] ?? {
            label: plain(clause.status),
            tone: "var(--secondary)",
            meaning: "",
          };
          return (
            <li key={clause.id} className="card p-5" data-testid={`rule-${clause.id}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <p className="t-body prose-measure">{clause.text}</p>
                <span className="badge badge-muted whitespace-nowrap" style={{ color: status.tone }}>
                  {status.label}
                </span>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-4">
                <Fact
                  label={<Term word="jurisdiction">Country</Term>}
                  value={jurisdictionName(clause.jurisdiction)}
                />
                <Fact label="Substance" value={clause.substance ?? "—"} />
                <Fact
                  label="Maximum allowed"
                  value={
                    clause.limit_value !== null && clause.limit_value !== undefined
                      ? `${clause.limit_value} ${plain(clause.unit_raw ?? "")}`
                      : "no number in this rule"
                  }
                />
                <Fact
                  label="From"
                  value={sourceById[clause.document_id] ?? "a document you added"}
                />
              </div>

              {status.meaning ? (
                <p className="t-footnote t-secondary mt-3">{status.meaning}</p>
              ) : null}

              <details className="mt-3">
                <summary className="t-caption cursor-pointer">Where this came from</summary>
                <p className="t-caption mono mt-1">{clause.id}</p>
                <Link href={`/documents/${clause.document_id}`} className="t-caption">
                  Open the document it was read from
                </Link>
              </details>
            </li>
          );
        })}
      </ul>
    </main>
  );
}

function Fact({ label, value }: { label: React.ReactNode; value: string }) {
  return (
    <div>
      <p className="t-footnote t-secondary">{label}</p>
      <p className="t-body mt-1" style={{ fontWeight: 600 }}>{value}</p>
    </div>
  );
}
