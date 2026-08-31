import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getRemediation,
  listDocuments,
  type RemediationLimit,
  type RemediationPlan,
  type RemediationTarget,
} from "@/lib/api";
import Provenance from "../../../_ui/Provenance";
import { marketName, plain } from "../../../_ui/status";
import PrintButton from "./PrintButton";

export const dynamic = "force-dynamic";

async function load(id: string): Promise<{
  plan: RemediationPlan;
  documents: Awaited<ReturnType<typeof listDocuments>>["documents"];
} | null> {
  try {
    const [plan, documents] = await Promise.all([
      getRemediation(id),
      // Source names only. If this fails the plan still renders, with ids
      // instead of the name of the regulation — never with nothing.
      listDocuments().then((r) => r.documents).catch(() => []),
    ]);
    return { plan, documents };
  } catch {
    return null;
  }
}

export default async function RemediationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await load(id);
  if (!data) notFound();
  const { plan, documents } = data;
  const sourceById = Object.fromEntries(documents.map((doc) => [doc.id, doc]));

  return (
    <main className="page page-mid" data-testid="remediation-page">
      <Link href={`/products/${id}`} className="btn btn-quiet btn-small -ml-2 no-print">
        ← Back to {plan.product_name}
      </Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="t-large-title">A plan to fix {plan.product_name}</h1>
          {/* Collaborative Partner, said out loud. The system prepared this; it
              did not do it, and nobody should have to infer that. */}
          <p className="t-body t-secondary mt-2 prose-measure" data-testid="draft-notice">
            <strong>This is a draft for you to check, not an action we took.</strong> Nothing has
            been changed, sent, or filed. The numbers below come from the rules we have read, and
            each one links to the exact wording it came from.
          </p>
        </div>
        <PrintButton />
      </div>

      {plan.targets.length === 0 ? (
        <section className="card mt-6 p-8 text-center" data-testid="remediation-empty">
          <p className="t-headline">Nothing is over a limit right now</p>
          <p className="t-subhead t-secondary mt-1 prose-measure mx-auto">
            No ingredient on {plan.product_name} breaks a rule in{" "}
            {listMarkets(plan.generated_for_markets)}, so there is no change to propose. What we
            could not check is listed below.
          </p>
        </section>
      ) : (
        <section className="mt-6 space-y-6" data-testid="targets">
          {plan.targets.map((target) => (
            <Target key={target.substance} target={target} plan={plan} sourceById={sourceById} />
          ))}
        </section>
      )}

      <NotChecked plan={plan} />

      <p className="t-caption t-secondary mt-6" data-testid="plan-trace">
        Prepared from the rules we hold at the time this page was opened. Reference:{" "}
        <span className="mono">{plan.trace_id ?? "—"}</span>
      </p>
    </main>
  );
}

/** One substance: the number to hit, every market's limit, and the wording. */
function Target({
  target,
  plan,
  sourceById,
}: {
  target: RemediationTarget;
  plan: RemediationPlan;
  sourceById: Record<string, { source_name?: string; jurisdiction?: string } | undefined>;
}) {
  const covered = plan.generated_for_markets.filter(
    (market) => !target.markets_without_rules.includes(market),
  );

  return (
    <article className="card p-6" data-testid={`target-${target.substance}`}>
      {/* --- The whole answer, in one sentence ---------------------------- */}
      {target.target_value !== null ? (
        <h2 className="t-title" data-testid={`headline-${target.substance}`}>
          Bring {target.substance_label} down to {round4(target.target_value)}{" "}
          {plain(target.target_unit)} or less, and this product is accepted in{" "}
          {listMarkets(covered)}.
        </h2>
      ) : (
        <h2 className="t-title" data-testid={`headline-${target.substance}`}>
          We cannot give you one number for {target.substance_label}.
        </h2>
      )}

      {target.no_target_reason ? (
        <p className="t-body t-secondary mt-2 prose-measure" data-testid={`no-target-${target.substance}`}>
          {target.no_target_reason_text}
        </p>
      ) : null}

      {target.coverage === "partial" ? (
        // Silence is the failure mode this line exists to prevent: a market we
        // hold no rule for must never read like a market that passed.
        <p
          className="inset mt-3 p-4 t-footnote"
          data-testid={`coverage-partial-${target.substance}`}
        >
          <strong>Not every market is in that number.</strong> We have no rule for{" "}
          {listMarkets(target.markets_without_rules)}, so {listMarkets(target.markets_without_rules)}{" "}
          is not covered by it. That is not a pass — it means nothing was checked there.
        </p>
      ) : null}

      {target.current_value !== null ? (
        <div className="mt-5 grid max-w-md grid-cols-2 gap-4">
          <div>
            <p className="t-footnote t-secondary">It has today</p>
            <p
              className="t-number figure mt-1"
              style={{ color: target.verdict_today === "fail" ? "var(--danger)" : "var(--good)" }}
              data-testid={`current-${target.substance}`}
            >
              {round4(target.current_value)}
              <span className="figure-unit">{plain(target.current_unit)}</span>
            </p>
          </div>
          <div>
            <p className="t-footnote t-secondary">It needs to be at most</p>
            <p className="t-number figure mt-1" data-testid={`target-value-${target.substance}`}>
              {target.target_value === null ? "—" : round4(target.target_value)}
              <span className="figure-unit">{plain(target.target_unit)}</span>
            </p>
          </div>
        </div>
      ) : null}

      {/* --- Every market's limit, and where it came from ------------------ */}
      {target.limits.length > 0 ? (
        <div className="mt-6 overflow-x-auto">
          {/* min-width, so a narrow screen scrolls the table rather than
              squeezing "In force from" into two clipped characters. */}
          <table
            className="w-full min-w-[520px] text-left"
            data-testid={`limits-${target.substance}`}
          >
            <thead>
              <tr className="row">
                <th className="t-footnote t-secondary py-2 pr-4">Market</th>
                <th className="t-footnote t-secondary py-2 pr-4">Most it allows</th>
                <th className="t-footnote t-secondary py-2 pr-4">Rule</th>
                <th className="t-footnote t-secondary py-2">In force from</th>
              </tr>
            </thead>
            <tbody>
              {target.limits.map((limit) => (
                <tr key={limit.market_id} className="row" data-testid={`limit-${limit.market_id}`}>
                  <td className="t-body py-3 pr-4">
                    {marketName(limit.market_id)}
                    {limit.is_strictest ? (
                      <span className="badge badge-warn ml-2" data-testid="strictest-flag">
                        strictest
                      </span>
                    ) : null}
                  </td>
                  <td className="t-body py-3 pr-4">
                    {round4(limit.limit)} {plain(limit.unit)}
                    {limit.other_limits_in_market > 0 ? (
                      <span className="t-caption t-secondary block">
                        {limit.other_limits_in_market} looser rule
                        {limit.other_limits_in_market === 1 ? "" : "s"} for it here as well
                      </span>
                    ) : null}
                  </td>
                  <td className="t-footnote py-3 pr-4">
                    {sourceById[limit.document_id ?? ""]?.source_name ?? "A document you added"}
                  </td>
                  <td className="t-footnote py-3">{limit.effective_date ?? "not stated"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {/* --- The words themselves ----------------------------------------- */}
      <div className="mt-6 space-y-4" data-testid={`quotes-${target.substance}`}>
        <h3 className="t-headline">What the rules actually say</h3>
        {target.limits.map((limit) => (
          <Quote key={`${limit.market_id}-${limit.clause_id}`} limit={limit} sourceById={sourceById} />
        ))}
      </div>
    </article>
  );
}

function Quote({
  limit,
  sourceById,
}: {
  limit: RemediationLimit;
  sourceById: Record<string, { source_name?: string; jurisdiction?: string } | undefined>;
}) {
  return (
    <div className="inset p-5" data-testid={`quote-${limit.clause_id}`}>
      <p className="t-footnote t-secondary">
        {marketName(limit.market_id)} ·{" "}
        {sourceById[limit.document_id ?? ""]?.source_name ?? "A document you added"}
      </p>
      {limit.quote ? (
        <blockquote className="t-body mt-2 prose-measure">“{limit.quote}”</blockquote>
      ) : (
        <p className="t-body t-secondary mt-2">
          We no longer hold the wording for this one. The limit above is what was read from it.
        </p>
      )}
      <Provenance
        clauseId={limit.clause_id}
        documentId={limit.document_id}
        sourceName={sourceById[limit.document_id ?? ""]?.source_name}
        jurisdiction={sourceById[limit.document_id ?? ""]?.jurisdiction}
        testId={`provenance-${limit.clause_id}`}
      />
    </div>
  );
}

/**
 * What we did not check.
 *
 * In the open, not behind a disclosure triangle. An ingredient list that
 * quietly loses the entries nothing was compared against reads exactly like a
 * clean bill of health, and this page is meant to be signed off.
 */
function NotChecked({ plan }: { plan: RemediationPlan }) {
  if (plan.not_checked.length === 0) return null;
  return (
    <section className="card mt-6 p-6" data-testid="not-checked">
      <h2 className="t-section">What we did not check</h2>
      <p className="t-subhead t-secondary mt-1 prose-measure">
        These ingredients were not compared against any limit. That is not the same as passing.
      </p>
      <ul className="mt-4">
        {plan.not_checked.map((row) => (
          <li key={row.ingredient} className="row py-3" data-testid={`not-checked-${row.reason_code}`}>
            <p className="t-body">{row.ingredient}</p>
            <p className="t-footnote t-secondary mt-1 prose-measure">{row.reason_text}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** "Germany (European Union) and Indonesia (BPOM)" — a list a person reads. */
function listMarkets(ids: string[]): string {
  const names = ids.map(marketName);
  if (names.length === 0) return "no market you have added yet";
  if (names.length === 1) return names[0];
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** Conversions produce long floats; nobody needs 200.00000000000003. */
function round4(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return String(Math.round(value * 10000) / 10000);
}
