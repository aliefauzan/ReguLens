import Link from "next/link";
import { notFound } from "next/navigation";
import { getCompliance, getProduct, getProductEvents, type ComplianceView, type GraphEvent } from "@/lib/api";
import AskPanel from "./AskPanel";
import { StatusBadge, countryName, marketName, plain, statusCopy } from "../../_ui/status";

export const dynamic = "force-dynamic";

async function load(
  id: string,
): Promise<{ product: ProductShape; events: GraphEvent[]; compliance: ComplianceView | null } | null> {
  try {
    let compliance: ComplianceView | null = null;
    try {
      compliance = await getCompliance(id);
    } catch {
      // Compliance view is additive; a 404 keeps the page usable.
    }
    const [{ product }, { events }] = await Promise.all([getProduct(id), getProductEvents(id)]);
    return { product, events, compliance };
  } catch {
    return null;
  }
}

export default async function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await load(id);
  if (!data) notFound();
  const { product, events, compliance } = data;

  return (
    <main className="mx-auto max-w-5xl px-5 py-8 sm:px-6 sm:py-12" data-testid="product-detail">
      <Link href="/" className="btn btn-quiet btn-small -ml-2">← All products</Link>

      <h1 className="t-large-title mt-3" data-testid="product-name">
        {product.name}
      </h1>
      <p className="t-body t-secondary mt-2">
        {plain(product.product_type)} · made in {countryName(product.origin)}
      </p>

      {/* --- The answer, first. Everything else explains it. ---------------- */}
      <section className="mt-8 space-y-4" data-testid="readiness-panel">
        <h2 className="t-section">Can you sell it?</h2>
        {compliance && Object.keys(compliance.statuses).length > 0 ? (
          Object.entries(compliance.statuses).map(([marketId, status]) => {
            const copy = statusCopy(status);
            const rows = compliance.requirements.filter((r) => r.market_id === marketId);
            const failing = rows.filter((r) => r.evaluation === "fail").length;
            const unchecked = rows.filter((r) => r.evaluation === "needs_review").length;
            return (
              <div key={marketId} className="card p-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h3 className="t-headline">{marketName(marketId)}</h3>
                  <StatusBadge status={status} />
                </div>
                <p className="t-subhead t-secondary mt-2">{copy.meaning}</p>

                {rows.length > 0 ? (
                  <ul className="mt-4 space-y-3" data-testid={`requirements-${marketId}`}>
                    {rows.map((req) => (
                      <li key={req.id} className="inset p-5">
                        <p className="t-headline">
                          <Mark evaluation={req.evaluation} />{" "}
                          {req.substance_normalized
                            ? req.substance_normalized.replaceAll("_", " ")
                            : plain(req.requirement_type ?? req.reason)}
                        </p>

                        {req.limit_value !== null && req.product_value !== null ? (
                          // The comparison is the whole answer. Show it as a
                          // comparison, at a size that survives a glance.
                          <div className="mt-4 grid max-w-md grid-cols-2 gap-4">
                            <div>
                              <p className="t-footnote t-secondary">Your product has</p>
                              <p
                                className="t-number figure mt-1"
                                style={{ color: req.evaluation === "fail" ? "var(--danger)" : "var(--good)" }}
                              >
                                {req.product_value}
                                <span className="figure-unit">{plain(req.unit)}</span>
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
                        ) : null}

                        <p className="t-footnote mt-3">
                          {req.evaluation === "fail"
                            ? "Over the limit — you cannot sell it here as it is."
                            : req.evaluation === "pass"
                              ? "Under the limit — this one is fine."
                              : req.reason === "non_numeric_clause"
                                ? "This rule has no number in it, so a person has to read it."
                                : "We do not know how much your product contains, so this was not checked."}
                        </p>

                        <Provenance clauseId={req.clause_id} />
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
            <p className="t-subhead t-secondary mt-1">
              We have not read any regulation for this product’s markets, so there is no answer to give.
              Adding one takes a minute.
            </p>
            <Link href="/documents/new" className="btn btn-primary btn-small mt-4">Add rules</Link>
          </div>
        )}
      </section>

      {/* --- Ask ------------------------------------------------------------ */}
      <AskPanel productId={id} />

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
                {ingredient.amount !== null
                  ? `${ingredient.amount} ${plain(ingredient.unit)}`
                  : "amount not given"}
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
              every change, and what caused it ({events.length})
            </span>
          </summary>
          <ol className="mt-4 space-y-2">
            {events.map((event) => (
              <li key={event.id} className="row py-3 t-footnote" data-testid={`event-${event.event_type}`}>
                <span className="t-subhead">{EVENT_WORDS[event.event_type] ?? plain(event.event_type)}</span>
                {event.before && event.after ? <DiffCell before={event.before} after={event.after} /> : null}
                {event.trace_id ? (
                  <span className="mono t-caption t-secondary ml-2">{event.trace_id.slice(0, 8)}</span>
                ) : null}
              </li>
            ))}
          </ol>
        </details>
      </section>
    </main>
  );
}

const EVENT_WORDS: Record<string, string> = {
  product_created: "Product added",
  product_status_changed: "Verdict changed",
  requirement_created: "Rule applied to this product",
  document_ingested: "Regulation added",
  clause_created: "Rule recorded",
  conflict_opened: "Two rules disagree",
};

/** Identifiers matter for an audit and mean nothing to a first-time reader. */
function Provenance({ clauseId }: { clauseId: string }) {
  return (
    <details className="mt-3">
      <summary className="t-caption cursor-pointer">Where this came from</summary>
      <p className="t-caption mono mt-1">{clauseId}</p>
    </details>
  );
}

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
