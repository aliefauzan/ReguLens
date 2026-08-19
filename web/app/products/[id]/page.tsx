import Link from "next/link";
import { notFound } from "next/navigation";
import { getProduct, getProductEvents, type GraphEvent, type Product } from "@/lib/api";

export const dynamic = "force-dynamic";

async function load(id: string): Promise<{ product: Product; events: GraphEvent[] } | null> {
  try {
    const [{ product }, { events }] = await Promise.all([getProduct(id), getProductEvents(id)]);
    return { product, events };
  } catch {
    return null;
  }
}

export default async function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await load(id);
  if (!data) notFound();
  const { product, events } = data;

  return (
    <main className="mx-auto max-w-3xl p-10" data-testid="product-detail">
      <Link href="/" className="text-sm underline opacity-70">
        ← All products
      </Link>

      <h1 className="mt-4 text-2xl font-semibold" data-testid="product-name">
        {product.name}
      </h1>

      <section className="mt-6 rounded border p-5" data-testid="compliance-twin">
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
            <dd data-testid="twin-markets">
              {product.target_markets.length ? product.target_markets.join(", ") : "—"}
            </dd>
          </div>
        </dl>

        <h3 className="mt-6 text-sm font-medium uppercase tracking-wide opacity-60">Ingredients</h3>
        <ul className="mt-3 space-y-2" data-testid="twin-ingredients">
          {product.ingredients.map((ingredient, index) => (
            <li
              key={`${ingredient.name}-${index}`}
              className="flex items-baseline justify-between rounded border px-3 py-2 text-sm"
              data-testid={`ingredient-${ingredient.normalized}`}
            >
              <span>
                {ingredient.name}
                <span className="ml-2 opacity-50">{ingredient.normalized}</span>
                {ingredient.unnormalized ? (
                  <span
                    className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900"
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

      <section className="mt-6 rounded border border-dashed p-5" data-testid="readiness-panel">
        <h2 className="text-sm font-medium uppercase tracking-wide opacity-60">Readiness</h2>
        <p className="mt-2 text-sm opacity-70">
          No regulatory data ingested yet. Nothing has been evaluated against this product, so
          there is no readiness figure to report.
        </p>
      </section>

      <section className="mt-6" data-testid="event-log">
        <h2 className="text-sm font-medium uppercase tracking-wide opacity-60">Audit trail</h2>
        <ul className="mt-3 space-y-2 text-sm">
          {events.map((event) => (
            <li key={event.id} className="rounded border px-3 py-2" data-testid={`event-${event.event_type}`}>
              <span className="font-medium">{event.event_type}</span>
              <span className="ml-2 opacity-60">by {event.triggered_by}</span>
              {event.trace_id ? (
                <span className="ml-2 font-mono text-xs opacity-40">{event.trace_id.slice(0, 8)}</span>
              ) : null}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
