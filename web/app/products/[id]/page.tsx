import Link from "next/link";
import { notFound } from "next/navigation";
import { getCompliance, getProduct, getProductEvents, type ComplianceView, type GraphEvent } from "@/lib/api";
import AskPanel from "./AskPanel";

export const dynamic = "force-dynamic";

const STATUS_STYLE: Record<string, { label: string; color: string; soft: string }> = {
  compliant: { label: "Compliant", color: "var(--accent)", soft: "var(--accent-soft)" },
  attention_required: { label: "Attention required", color: "var(--warn)", soft: "var(--warn-soft)" },
  non_compliant: { label: "Non-compliant", color: "var(--danger)", soft: "var(--danger-soft)" },
  unknown: { label: "No regulatory data", color: "var(--muted)", soft: "transparent" },
};

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
    <main className="mx-auto max-w-5xl p-10" data-testid="product-detail">
      <div className="flex items-baseline justify-between">
        <Link href="/" className="text-sm underline opacity-70">← All products</Link>
        <span className="font-mono text-xs opacity-40">{id}</span>
      </div>

      <h1 className="mt-4 text-2xl font-semibold tracking-tight" data-testid="product-name">
        {product.name}
      </h1>

      <section className="card mt-6 p-5" data-testid="compliance-twin">
        <h2 className="text-sm font-medium uppercase tracking-wide opacity-60">Compliance twin</h2>
        <dl className="mt-4 grid gap-3 sm:grid-cols-2">
          <div>
            <dt className="text-sm opacity-60">Product type</dt>
            <dd data-testid="twin-product-type">{product.product_type.replaceAll("_", " ")}</dd>
          </div>
          <div>
            <dt className="text-sm opacity-60">Origin</dt>
            <dd data-testid="twin-origin">{product.origin}</dd>
          </div>
          <div>
            <dt className="text-sm opacity-60">Packaging</dt>
            <dd data-testid="twin-packaging">{product.packaging ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-sm opacity-60">Destination markets</dt>
            <dd data-testid="twin-markets">{product.target_markets.join(", ") || "—"}</dd>
          </div>
        </dl>
        <h3 className="mt-6 text-sm font-medium uppercase tracking-wide opacity-60">Ingredients</h3>
        <ul className="mt-3 space-y-2" data-testid="twin-ingredients">
          {product.ingredients.map((ingredient, index) => (
            <li key={`${ingredient.name}-${index}`} className="flex items-baseline justify-between text-sm" >
              <span>
                {ingredient.name}
                <span className="ml-2 opacity-50">{ingredient.normalized}</span>
                {ingredient.unnormalized ? (
                  <span
                    className="ml-2 rounded-full px-1.5 py-0.5 text-xs"
                    style={{ background: "var(--warn-soft)", color: "var(--warn)" }}
                    title="Not in the substance dictionary — it will not match any clause"
                    data-testid="unnormalized-flag"
                  >
                    unrecognised
                  </span>
                ) : null}
              </span>
              <span className="opacity-70">
                {ingredient.amount !== null ? `${ingredient.amount} ${ingredient.unit}` : "—"}
              </span>
            </li>
          ))}
        </ul>
      </section>

      {/* Readiness per market */}
      <section className="mt-6 space-y-4" data-testid="readiness-panel">
        {compliance && Object.keys(compliance.statuses).length > 0 ? (
          Object.entries(compliance.statuses).map(([marketId, status]) => (
            <div key={marketId} className="card p-5">
              <div className="flex items-baseline justify-between">
                <h2 className="font-medium">{marketId}</h2>
                <StatusBadge status={status} />
              </div>
              <ul className="mt-3 space-y-2 text-sm" data-testid={`requirements-${marketId}`}>
                {compliance.requirements
                  .filter((r) => r.market_id === marketId)
                  .map((req) => (
                    <li key={req.id} className="flex items-baseline justify-between gap-3">
                      <span>
                        <Mark evaluation={req.evaluation} />{" "}
                        <span className="font-mono text-xs opacity-70">{req.clause_id}</span>{" "}
                        {req.substance_normalized ?? req.reason ?? ""}
                        {req.limit_value !== null ? (
                          <span className="opacity-70">
                            {" "}
                            · limit {req.limit_value} {req.unit}
                          </span>
                        ) : null}
                      </span>
                      <span className="opacity-70">
                        {req.product_value !== null ? `product ${req.product_value} ${req.unit}` : "amount unknown"}
                      </span>
                    </li>
                  ))}
              </ul>
              <p className="mt-3 text-xs opacity-60" data-testid={`issues-${marketId}`}>
                {compliance.issue_counts.total > 0
                  ? `${compliance.issue_counts.total} issues — ${compliance.issue_counts.critical} critical`
                  : "no issues"}
              </p>
            </div>
          ))
        ) : (
          <div className="card p-5 text-sm opacity-70" data-testid="readiness-empty">
            No regulatory data ingested yet. Nothing has been evaluated against this product,
            so there is no readiness figure to report.
          </div>
        )}
      </section>

      {/* Ask panel */}
      <AskPanel productId={id} />

      {/* Timeline */}
      <section className="mt-10" data-testid="event-log">
        <h2 className="text-sm font-medium uppercase tracking-wide opacity-60">Audit trail</h2>
        <ol className="mt-3 space-y-2 text-sm">
          {events.map((event) => (
            <li key={event.id} className="card px-3 py-2" data-testid={`event-${event.event_type}`}>
              <span className="font-medium">{event.event_type}</span>
              {event.before && event.after ? (
                <DiffCell before={event.before} after={event.after} />
              ) : null}
              {event.trace_id ? (
                <span className="ml-2 font-mono text-xs opacity-40">{event.trace_id.slice(0, 8)}</span>
              ) : null}
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}

function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLE[status] ?? STATUS_STYLE.unknown;
  return (
    <span
      className="rounded-full px-2.5 py-0.5 text-xs font-medium"
      style={{ color: style.color, background: style.soft }}
      data-testid={`status-${status}`}
    >
      {style.label}
    </span>
  );
}

function Mark({ evaluation }: { evaluation: string }) {
  const glyph = evaluation === "pass" ? "✓" : evaluation === "fail" ? "✕" : "⚠";
  return (
    <span
      aria-label={evaluation}
      style={{
        color:
          evaluation === "pass" ? "var(--accent)"
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
      <span className="ml-2 font-mono text-xs">
        {String(b.limit_value)} → {String(a.limit_value)}
      </span>
    );
  }
  if (b.status_map || a.status_map) {
    const bm = b.status_map ?? {};
    const am = a.status_map ?? {};
    const changed = Object.keys(am)
      .filter((k) => bm[k] !== am[k])
      .map((k) => `${k}: ${bm[k] ?? "?"} → ${am[k]}`);
    if (changed.length) return <span className="ml-2 font-mono text-xs">{changed.join(", ")}</span>;
  }
  if (b.status !== a.status) {
    const worsened =
      a.status === "non_compliant" ||
      (a.status === "attention_required" && b.status !== "non_compliant");
    return (
      <span
        className="ml-2 font-mono text-xs"
        style={worsened ? { color: "var(--danger)", fontWeight: 600 } : undefined}
        data-testid="status-transition"
      >
        {String(b.status)} → {String(a.status)}
      </span>
    );
  }
  return null;
}

type ProductShape = Awaited<ReturnType<typeof getProduct>>["product"];
