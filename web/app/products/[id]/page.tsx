import Link from "next/link";
import { LoadStarterRules } from "../../_ui/Rulebook";
import { notFound } from "next/navigation";
import {
  getCompliance,
  getProduct,
  getProductEvents,
  listDocuments,
  type ComplianceRequirement,
  type ComplianceView,
  type GraphEvent,
} from "@/lib/api";
import AskPanel from "./AskPanel";
import Provenance from "../../_ui/Provenance";
import ProductActions from "./ProductActions";
import { StatusBadge, countryName, marketName, plain, readableDate, statusCopy } from "../../_ui/status";

export const dynamic = "force-dynamic";

// A requirement the reader can see but that does not count toward today's
// verdict. Without this the page shows a red row under a green badge and
// explains nothing, which is the one thing this project promised not to do.
function startsLater(req: ComplianceRequirement, today: string): boolean {
  const when = req.effective_date?.slice(0, 10);
  return Boolean(when && /^\d{4}-\d{2}-\d{2}$/.test(when) && when > today);
}

async function load(
  id: string,
): Promise<{
  product: ProductShape;
  events: GraphEvent[];
  compliance: ComplianceView | null;
  documents: Awaited<ReturnType<typeof listDocuments>>["documents"];
} | null> {
  try {
    let compliance: ComplianceView | null = null;
    try {
      compliance = await getCompliance(id);
    } catch {
      // Compliance view is additive; a 404 keeps the page usable.
    }
    const [{ product }, { events }, documents] = await Promise.all([
      getProduct(id),
      getProductEvents(id),
      // Names for the documents behind each rule. Additive: if this fails the
      // page still renders, just without the source names.
      listDocuments().then((r) => r.documents).catch(() => []),
    ]);
    return { product, events, compliance, documents };
  } catch {
    return null;
  }
}

/**
 * What to change so this row passes, as a number.
 *
 * "Over the limit — you cannot sell it here as it is" tells a reader they have
 * a problem and not what to do about it. The limit is already on screen; what
 * is missing is the instruction, and the strictest number across the markets
 * they actually sell into — meeting that one meets all of them.
 */
function remediation(
  req: ComplianceRequirement,
  all: ComplianceRequirement[],
): { target: string; strictest: { value: number; unit: string; marketId: string } | null } | null {
  if (req.evaluation !== "fail") return null;
  const limit = req.comparable_limit ?? req.limit_value;
  const unit = req.comparable_unit ?? req.unit;
  if (limit === null || limit === undefined || !unit) return null;

  // Only limits expressed in the same unit can be ranked against each other;
  // an unconvertible one is left out rather than guessed at.
  const comparable = all.filter(
    (other) =>
      other.substance_normalized === req.substance_normalized &&
      (other.comparable_unit ?? other.unit) === unit &&
      (other.comparable_limit ?? other.limit_value) !== null,
  );
  const valueOf = (other: ComplianceRequirement) =>
    (other.comparable_limit ?? other.limit_value) as number;
  const lowestIn = (rows: ComplianceRequirement[]) =>
    rows.reduce<ComplianceRequirement | null>(
      (best, other) => (best === null || valueOf(other) < valueOf(best) ? other : best),
      null,
    );

  // Meeting the strictest rule in this market is what "you can sell it here"
  // means — quoting the rule that happens to be on screen would leave the
  // reader failing a second one they were never told about.
  const here = lowestIn(comparable.filter((other) => other.market_id === req.market_id));
  const target = here ? Math.min(valueOf(here), limit) : limit;

  // Only *other* markets can be "stricter still". Saying Germany is stricter
  // than Germany reads as a bug, because it is one.
  const elsewhere = lowestIn(comparable.filter((other) => other.market_id !== req.market_id));

  return {
    target: `${round4(target)} ${plain(unit)}`,
    strictest:
      elsewhere && valueOf(elsewhere) < target
        ? { value: valueOf(elsewhere), unit, marketId: elsewhere.market_id }
        : null,
  };
}

export default async function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await load(id);
  if (!data) notFound();
  const { product, events, compliance, documents } = data;
  const today = new Date().toISOString().slice(0, 10);
  const sourceById = Object.fromEntries(documents.map((doc) => [doc.id, doc]));

  return (
    <main className="mx-auto max-w-5xl px-5 py-8 sm:px-6 sm:py-12" data-testid="product-detail">
      <Link href="/" className="btn btn-quiet btn-small -ml-2">← All products</Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="t-large-title" data-testid="product-name">
            {product.name}
          </h1>
          <p className="t-body t-secondary mt-2">
            {plain(product.product_type)} · made in {countryName(product.origin)}
          </p>
        </div>
        <ProductActions productId={id} productName={product.name} />
      </div>

      {/* --- The answer, first. Everything else explains it. ---------------- */}
      <section className="mt-8 space-y-4" data-testid="readiness-panel">
        <h2 className="t-section">Can you sell it?</h2>
        {compliance && Object.keys(compliance.statuses).length > 0 ? (
          Object.entries(compliance.statuses).map(([marketId, status]) => {
            const copy = statusCopy(status);
            // Worst first. A labelling note that needs a human should not sit
            // above the ingredient that is actually over the limit.
            const severityRank = (evaluation: string) =>
              evaluation === "fail" ? 0 : evaluation === "needs_review" ? 1 : 2;
            const rows = compliance.requirements
              .filter((r) => r.market_id === marketId)
              .sort((a, b) => severityRank(a.evaluation) - severityRank(b.evaluation));
            const failing = rows.filter((r) => r.evaluation === "fail").length;
            const unchecked = rows.filter((r) => r.evaluation === "needs_review").length;

            // One ingredient, one card. A rulebook holds several limits for the
            // same substance in the same market — the flavoured-drink row, the
            // juice row, the concentrate row — and showing six near-identical
            // cards buries the one that decides the answer. The strictest (or
            // the failing one) leads; the rest are one line each underneath, so
            // nothing is hidden.
            const groupKey = (r: ComplianceRequirement) =>
              r.substance_normalized ?? `${r.requirement_type ?? r.reason ?? "rule"}:${r.id}`;
            const grouped = new Map<string, ComplianceRequirement[]>();
            for (const row of rows) {
              const key = groupKey(row);
              grouped.set(key, [...(grouped.get(key) ?? []), row]);
            }
            const limitOf = (r: ComplianceRequirement) =>
              (r.comparable_limit ?? r.limit_value ?? Infinity) as number;
            const primaries: ComplianceRequirement[] = [];
            const othersByKey = new Map<string, ComplianceRequirement[]>();
            for (const [key, group] of grouped) {
              const ordered = [...group].sort(
                (a, b) =>
                  severityRank(a.evaluation) - severityRank(b.evaluation) ||
                  limitOf(a) - limitOf(b),
              );
              primaries.push(ordered[0]);
              othersByKey.set(key, ordered.slice(1));
            }
            primaries.sort((a, b) => severityRank(a.evaluation) - severityRank(b.evaluation));
            return (
              <div key={marketId} className="card p-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h3 className="t-headline">{marketName(marketId)}</h3>
                  <StatusBadge status={status} />
                </div>
                <p className="t-subhead t-secondary mt-2">{copy.meaning}</p>
                {compliance.upcoming?.[marketId] ? (
                  // The pair is the point. "Compliant" alone is true and
                  // useless when a rule already adopted changes the answer on a
                  // date, and that date is the only window anybody can act in.
                  <p
                    className="t-subhead mt-3"
                    style={{ color: "var(--warn)", fontWeight: 600 }}
                    data-testid={`upcoming-${marketId}`}
                  >
                    Changes on {readableDate(compliance.upcoming[marketId].effective_date)}:{" "}
                    {statusCopy(compliance.upcoming[marketId].status).label.toLowerCase()}.{" "}
                    <span style={{ fontWeight: 400 }}>
                      {statusCopy(compliance.upcoming[marketId].status).meaning}
                    </span>{" "}
                    {compliance.upcoming[marketId].document_id ? (
                      <Link
                        className="underline"
                        style={{ fontWeight: 400 }}
                        href={`/documents/${compliance.upcoming[marketId].document_id}${
                          compliance.upcoming[marketId].clause_id
                            ? `?cite=${compliance.upcoming[marketId].clause_id}`
                            : ""
                        }`}
                        data-testid={`upcoming-source-${marketId}`}
                      >
                        Read the rule that sets this date
                      </Link>
                    ) : null}
                  </p>
                ) : null}

                {rows.length > 0 ? (
                  <ul className="mt-4 space-y-3" data-testid={`requirements-${marketId}`}>
                    {primaries.map((req) => (
                      <li key={req.id} className="inset p-5">
                        <p className="t-headline">
                          <Mark evaluation={req.evaluation} />{" "}
                          {req.substance_normalized
                            ? req.substance_normalized.replaceAll("_", " ")
                            : plain(req.requirement_type ?? req.reason)}
                        </p>
                        {startsLater(req, today) ? (
                          <p
                            className="t-footnote t-secondary mt-1"
                            data-testid="requirement-not-yet-in-force"
                          >
                            Not in force yet — this one starts on{" "}
                            {readableDate(req.effective_date)}, so it is not part of
                            today’s verdict.
                          </p>
                        ) : null}

                        {req.limit_value !== null && req.product_value !== null ? (
                          // The comparison is the whole answer. Show it as a
                          // comparison, at a size that survives a glance — and
                          // in the unit the comparison was actually made in.
                          <>
                            <div className="mt-4 grid max-w-md grid-cols-2 gap-4">
                              <div>
                                <p className="t-footnote t-secondary">Your product has</p>
                                <p
                                  className="t-number figure mt-1"
                                  style={{ color: req.evaluation === "fail" ? "var(--danger)" : "var(--good)" }}
                                >
                                  {req.product_value}
                                  <span className="figure-unit">{plain(req.product_unit ?? req.unit)}</span>
                                </p>
                              </div>
                              <div>
                                <p className="t-footnote t-secondary">Allowed up to</p>
                                <p className="t-number figure mt-1">
                                  {req.limit_value}
                                  <span className="figure-unit">{plain(req.unit)}</span>
                                </p>
                              </div>
                            </div>
                            {req.product_unit && req.product_unit !== req.unit && req.comparable_value != null ? (
                              <p className="t-footnote t-secondary mt-2">
                                In the same unit: {round4(req.comparable_value)} {plain(req.comparable_unit)} against{" "}
                                {round4(req.comparable_limit)} {plain(req.comparable_unit)}.
                              </p>
                            ) : null}
                          </>
                        ) : null}

                        <p className="t-footnote mt-3">
                          {req.evaluation === "fail"
                            ? "Over the limit — you cannot sell it here as it is."
                            : req.evaluation === "pass"
                              ? "Under the limit — this one is fine."
                              : req.reason === "non_numeric_clause"
                                ? "This rule has no number in it, so a person has to read it."
                                : "We do not know how much your product contains, so this was not checked."}
                          {req.evaluation === "needs_review" && req.reason !== "non_numeric_clause" ? (
                            <>
                              {" "}
                              <Link href={`/products/${id}/edit`} data-testid={`fill-amount-${req.id}`}>
                                Fill in the amount
                              </Link>{" "}
                              and it will be.
                            </>
                          ) : null}
                        </p>

                        {(() => {
                          const fix = remediation(req, compliance.requirements);
                          if (fix === null) return null;
                          return (
                            <p className="inset mt-3 p-4 t-footnote" data-testid={`fix-${req.id}`}>
                              <strong>To pass here:</strong> bring it down to {fix.target} or less.
                              {fix.strictest ? (
                                <>
                                  {" "}
                                  {marketName(fix.strictest.marketId)} is stricter still at{" "}
                                  {round4(fix.strictest.value)} {plain(fix.strictest.unit)} — meet that
                                  one and you meet both.
                                </>
                              ) : null}
                            </p>
                          );
                        })()}

                        {/* Which rule this number is. With a rulebook loaded a
                            market can hold several limits for one substance,
                            and "150 mg per kg" means nothing until you know it
                            is the flavoured-drinks row rather than the juice
                            one. */}
                        {sourceById[req.document_id ?? ""]?.source_name ? (
                          <p className="t-caption t-secondary mt-3" data-testid={`rule-name-${req.id}`}>
                            From {sourceById[req.document_id ?? ""]?.source_name}
                          </p>
                        ) : null}

                        <Provenance
                          clauseId={req.clause_id}
                          documentId={req.document_id}
                          sourceName={sourceById[req.document_id ?? ""]?.source_name}
                          jurisdiction={req.jurisdiction ?? sourceById[req.document_id ?? ""]?.jurisdiction}
                          testId={`provenance-${req.id}`}
                        />

                        {(othersByKey.get(groupKey(req)) ?? []).length > 0 ? (
                          <details className="mt-2" data-testid={`other-limits-${req.id}`}>
                            <summary className="t-footnote cursor-pointer">
                              {(othersByKey.get(groupKey(req)) ?? []).length} more limit
                              {(othersByKey.get(groupKey(req)) ?? []).length === 1 ? "" : "s"} for this
                              ingredient here
                            </summary>
                            <ul className="mt-2 space-y-2">
                              {(othersByKey.get(groupKey(req)) ?? []).map((other) => (
                                <li key={other.id} className="t-footnote t-secondary">
                                  <Mark evaluation={other.evaluation} />{" "}
                                  {other.limit_value !== null
                                    ? `${other.limit_value} ${plain(other.unit)}`
                                    : plain(other.reason ?? "no number")}
                                  {sourceById[other.document_id ?? ""]?.source_name
                                    ? ` — ${sourceById[other.document_id ?? ""]?.source_name}`
                                    : ""}
                                  {other.document_id ? (
                                    <>
                                      {" "}
                                      <Link
                                        href={`/documents/${other.document_id}?cite=${other.clause_id}`}
                                        data-testid={`open-other-${other.id}`}
                                      >
                                        show it
                                      </Link>
                                    </>
                                  ) : null}
                                </li>
                              ))}
                            </ul>
                          </details>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : null}

                <p className="t-footnote t-secondary mt-5" data-testid={`issues-${marketId}`}>
                  {failing > 0 || unchecked > 0
                    ? `${failing} rule${failing === 1 ? "" : "s"} broken · ${unchecked} to check by hand`
                    : "No problems found"}
                </p>
              </div>
            );
          })
        ) : (
          <div className="card p-8 text-center" data-testid="readiness-empty">
            <p className="t-headline">Nothing to compare against yet</p>
            <p className="t-subhead t-secondary mt-1 prose-measure mx-auto">
              We have not read any regulation for this product’s markets yet. You do not have to go
              and find one: ReguLens ships with the EU and Indonesian additive rules.
            </p>
            <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
              <LoadStarterRules />
              <Link href="/documents/new" className="btn btn-secondary btn-small">
                Or read my own document
              </Link>
            </div>
          </div>
        )}
      </section>

      {/* --- Ask ------------------------------------------------------------ */}
      <AskPanel
        productId={id}
        productName={product.name}
        failingMarket={
          Object.entries(compliance?.statuses ?? {}).find(
            ([, status]) => status === "non_compliant",
          )?.[0] ?? null
        }
        markets={product.target_markets}
      />

      {/* --- What we know about the product --------------------------------- */}
      <section className="card mt-10 p-6" data-testid="compliance-twin">
        <h2 className="t-section">What we know about this product</h2>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">
          <Fact label="Kind of product" testId="twin-product-type" value={plain(product.product_type)} />
          <Fact label="Made in" testId="twin-origin" value={countryName(product.origin)} />
          <Fact label="Packaging" testId="twin-packaging" value={product.packaging ?? "—"} />
          <Fact
            label="Selling into"
            testId="twin-markets"
            value={product.target_markets.map(marketName).join(", ") || "—"}
          />
        </dl>

        <h3 className="t-headline mt-8">Ingredients</h3>
        <ul className="mt-3" data-testid="twin-ingredients">
          {product.ingredients.map((ingredient, index) => (
            <li key={`${ingredient.name}-${index}`} className="row flex items-baseline justify-between gap-3 py-3">
              <span className="t-body">
                {ingredient.name}
                {ingredient.unnormalized ? (
                  <span
                    className="badge badge-warn ml-2"
                    title="We do not recognise this name, so no rule can be matched to it. Try the common name or its E-number."
                    data-testid="unnormalized-flag"
                  >
                    not recognised
                  </span>
                ) : null}
              </span>
              <span className="t-footnote t-secondary">
                {ingredient.amount !== null ? (
                  `${ingredient.amount} ${plain(ingredient.unit)}`
                ) : (
                  <Link href={`/products/${id}/edit`}>add an amount</Link>
                )}
              </span>
            </li>
          ))}
        </ul>
      </section>

      {/* --- History: available, but folded away for a first-time reader ---- */}
      <section className="mt-8" data-testid="event-log">
        <details className="card p-5">
          <summary className="t-headline cursor-pointer">
            Full history
            <span className="t-footnote t-secondary ml-2">
              every change, and what caused it ({readableEvents(events).length})
            </span>
          </summary>
          <ol className="mt-4 space-y-2">
            {readableEvents(events).map((event) => (
              <li key={event.id} className="row py-3 t-footnote" data-testid={`event-${event.event_type}`}>
                <span className="t-subhead">{EVENT_WORDS[event.event_type] ?? plain(event.event_type)}</span>
                {event.before && event.after ? <DiffCell before={event.before} after={event.after} /> : null}
                <span className="t-caption t-secondary ml-2">{when(event.occurred_at)}</span>
              </li>
            ))}
          </ol>
          <p className="t-caption t-secondary mt-4">
            Every entry above is a change ReguLens made and why. Nothing here can be edited.
          </p>
        </details>
      </section>
    </main>
  );
}

/**
 * The history a person can read.
 *
 * Two things made it unreadable. Rows where the verdict did not actually change
 * ("No rules added yet → No rules added yet") are a side effect of writing one
 * event per market, and they outnumbered the real ones. And every row ended in
 * eight characters of hexadecimal — the trace id, which is ours, not theirs.
 */
function readableEvents(events: GraphEvent[]): GraphEvent[] {
  return events.filter((event) => {
    const before = (event.before as { status?: string } | null)?.status;
    const after = (event.after as { status?: string } | null)?.status;
    if (before === undefined && after === undefined) return true;
    // Compare the words the reader sees, not the values underneath. A first
    // evaluation writes `null → "unknown"`, which is a real difference in the
    // data and the identical sentence on screen: "No rules added yet → No
    // rules added yet", printed once per market.
    return statusCopy(before).label !== statusCopy(after).label;
  });
}

/** A timestamp people read, not an ISO string. */
function when(occurredAt: string | null): string {
  if (!occurredAt) return "";
  const then = new Date(occurredAt).getTime();
  if (Number.isNaN(then)) return "";
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  return new Date(occurredAt).toLocaleDateString();
}

const EVENT_WORDS: Record<string, string> = {
  product_created: "Product added",
  product_status_changed: "Verdict changed",
  requirement_created: "Rule applied to this product",
  document_ingested: "Regulation added",
  clause_created: "Rule recorded",
  conflict_opened: "Two rules disagree",
};

/** Conversions produce long floats; nobody needs 200.00000000000003. */
function round4(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return String(Math.round(value * 10000) / 10000);
}

/** Identifiers matter for an audit and mean nothing to a first-time reader. */

function Fact({ label, value, testId }: { label: string; value: string; testId: string }) {
  return (
    <div>
      <dt className="t-footnote t-secondary">{label}</dt>
      <dd className="t-body mt-1" data-testid={testId}>{value}</dd>
    </div>
  );
}

function Mark({ evaluation }: { evaluation: string }) {
  const glyph = evaluation === "pass" ? "✓" : evaluation === "fail" ? "✕" : "⚠";
  const label = evaluation === "pass" ? "passes" : evaluation === "fail" ? "fails" : "needs a person";
  return (
    <span
      aria-label={label}
      style={{
        color:
          evaluation === "pass" ? "var(--good)"
          : evaluation === "fail" ? "var(--danger)"
          : "var(--warn)",
      }}
    >
      {glyph}
    </span>
  );
}

type DiffSide = { status?: string; limit_value?: number; market?: string; status_map?: Record<string, string> };

function DiffCell({ before, after }: { before: unknown; after: unknown }) {
  const b = (before ?? {}) as DiffSide;
  const a = (after ?? {}) as DiffSide;
  if (b.limit_value !== undefined || a.limit_value !== undefined) {
    return (
      <span className="mono t-caption ml-2">
        {String(b.limit_value)} → {String(a.limit_value)}
      </span>
    );
  }
  if (b.status_map || a.status_map) {
    const bm = b.status_map ?? {};
    const am = a.status_map ?? {};
    const changed = Object.keys(am)
      .filter((k) => bm[k] !== am[k])
      .map((k) => `${marketName(k)}: ${statusCopy(bm[k]).label} → ${statusCopy(am[k]).label}`);
    if (changed.length) return <span className="t-caption ml-2">{changed.join(", ")}</span>;
  }
  if (b.status !== a.status) {
    const worsened =
      a.status === "non_compliant" ||
      (a.status === "attention_required" && b.status !== "non_compliant");
    return (
      <span
        className="t-caption ml-2"
        style={worsened ? { color: "var(--danger)", fontWeight: 600 } : { color: "var(--secondary)" }}
        data-testid="status-transition"
      >
        {statusCopy(b.status).label} → {statusCopy(a.status).label}
      </span>
    );
  }
  return null;
}

type ProductShape = Awaited<ReturnType<typeof getProduct>>["product"];
