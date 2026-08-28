import Link from "next/link";
import { listClauses, listConflicts, type Clause, type Conflict } from "@/lib/api";
import Term from "../_ui/Term";
import { jurisdictionName, plain } from "../_ui/status";

export const dynamic = "force-dynamic";

export default async function ConflictsPage() {
  let conflicts: Conflict[] = [];
  let byId: Record<string, Clause> = {};
  let error: string | null = null;
  try {
    // The conflict record stores ids; a reader needs countries and wording, so
    // join the clauses here rather than teaching the reader what an id is.
    const [conflictResult, clauseResult] = await Promise.all([listConflicts(), listClauses({})]);
    conflicts = conflictResult.conflicts;
    byId = Object.fromEntries(clauseResult.clauses.map((c) => [c.id, c]));
  } catch {
    error = "We could not reach the ReguLens service. Check that it is running, then reload this page.";
  }

  return (
    <main className="mx-auto max-w-5xl px-5 py-8 sm:px-6 sm:py-12" data-testid="conflicts-page">
      <h1 className="t-large-title">Rules that disagree</h1>
      <p className="t-body t-secondary prose-measure mt-2">
        Two countries can allow different amounts of the same ingredient. Neither rule is wrong —
        they simply apply in different <Term word="jurisdiction">jurisdictions</Term>. To sell in
        both, follow the stricter one.
      </p>

      {error ? (
        <div className="card mt-8 p-5" data-testid="conflicts-error">
          <p className="t-headline" style={{ color: "var(--danger)" }}>Service unavailable</p>
          <p className="t-footnote t-secondary mt-1">{error}</p>
        </div>
      ) : null}

      {conflicts.length === 0 && !error ? (
        <div className="card mt-8 p-8 text-center" data-testid="conflicts-empty">
          <p className="t-headline">Nothing disagrees right now</p>
          <p className="t-footnote t-secondary mt-1">
            None of the rules you have added contradict each other across countries.
          </p>
          <Link href="/documents/new" className="btn btn-secondary btn-small mt-4">Add more rules</Link>
        </div>
      ) : null}

      <ul className="mt-8 space-y-4">
        {conflicts.map((conflict) => {
          const a = Number(conflict.detail?.a_limit);
          const b = Number(conflict.detail?.b_limit);
          const stricter = Number.isFinite(a) && Number.isFinite(b) ? (a < b ? "a" : "b") : null;
          return (
            <li key={conflict.id} className="card p-6" data-testid={`conflict-${conflict.id}`}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="t-section">{plain(conflict.type)}</h2>
                <span className="badge badge-danger">{conflict.severity === "high" ? "Important" : conflict.severity}</span>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <Side
                  testId={`conflict-a-${conflict.id}`}
                  clause={byId[conflict.clause_a]}
                  clauseId={conflict.clause_a}
                  limit={conflict.detail?.a_limit}
                  unit={conflict.detail?.a_unit}
                  strictest={stricter === "a"}
                />
                <Side
                  testId={`conflict-b-${conflict.id}`}
                  clause={byId[conflict.clause_b]}
                  clauseId={conflict.clause_b}
                  limit={conflict.detail?.b_limit}
                  unit={conflict.detail?.b_unit}
                  strictest={stricter === "b"}
                />
              </div>

              {stricter ? (
                <p className="inset mt-4 p-5 t-body">
                  <strong>What to do:</strong> stay at or below{" "}
                  {String(stricter === "a" ? conflict.detail?.a_limit : conflict.detail?.b_limit)}{" "}
                  {plain(String(stricter === "a" ? conflict.detail?.a_unit : conflict.detail?.b_unit))} and the
                  product is acceptable in both places.
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </main>
  );
}

function Side({
  testId,
  clause,
  clauseId,
  limit,
  unit,
  strictest,
}: {
  testId: string;
  clause?: Clause;
  clauseId: string;
  limit: unknown;
  unit: unknown;
  strictest: boolean;
}) {
  return (
    <div
      className="inset p-4"
      style={strictest ? { boxShadow: "inset 0 0 0 2px var(--accent)" } : undefined}
      data-testid={testId}
    >
      <p className="t-headline">{jurisdictionName(clause?.jurisdiction)}</p>
      <p className="t-footnote t-secondary mt-3">Maximum allowed</p>
      <p className="t-number figure mt-1">
        {String(limit ?? "—")}
        <span className="figure-unit">{plain(unit as string)}</span>
      </p>
      {strictest ? <span className="badge badge-muted mt-3">Stricter — follow this one</span> : null}
      {clause?.text ? (
        <p className="t-footnote t-secondary mt-4">“{clause.text}”</p>
      ) : null}
      <details className="mt-3">
        <summary className="t-caption cursor-pointer">Where this came from</summary>
        <p className="t-caption mono mt-1">{clauseId}</p>
      </details>
    </div>
  );
}
