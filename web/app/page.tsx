import Link from "next/link";
import { getCompliance, listDocuments, listProducts, type ComplianceView, type Product } from "@/lib/api";
import AlertsBanner from "./AlertsBanner";
import { StatusBadge, marketName, jurisdictionName, plain } from "./_ui/status";

export const dynamic = "force-dynamic";

type Row = { product: Product; compliance: ComplianceView | null };

async function loadAll(): Promise<{
  rows: Row[];
  docs: Awaited<ReturnType<typeof listDocuments>>["documents"];
  error: string | null;
}> {
  try {
    const [{ products }, { documents }] = await Promise.all([listProducts(), listDocuments()]);
    const rows = await Promise.all(
      products.map(async (product) => {
        try {
          return { product, compliance: await getCompliance(product.id) };
        } catch {
          // A missing compliance view must not hide the product itself.
          return { product, compliance: null };
        }
      }),
    );
    return { rows, docs: documents, error: null };
  } catch {
    // An unreachable API and an empty account must never look the same.
    return { rows: [], docs: [], error: "We could not reach the ReguLens service. Check that it is running, then reload this page." };
  }
}

export default async function Home() {
  const { rows, docs, error } = await loadAll();
  const firstRun = rows.length === 0 && !error;

  return (
    <main className="mx-auto max-w-5xl px-5 py-8 sm:px-6 sm:py-12" data-testid="home">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="t-large-title">Your products</h1>
          <p className="t-subhead t-secondary mt-2 max-w-xl">
            Each product is checked against the rules of every market you sell into.
            When a new rule arrives, the answer here updates by itself.
          </p>
        </div>
        <Link href="/products/new" className="btn btn-primary" data-testid="new-product-link">
          Add a product
        </Link>
      </header>

      <AlertsBanner />

      {error ? (
        <div className="card mt-8 p-5" data-testid="products-error">
          <p className="t-headline" style={{ color: "var(--danger)" }}>Service unavailable</p>
          <p className="t-subhead t-secondary mt-1">{error}</p>
        </div>
      ) : null}

      {firstRun ? <StartHere /> : null}

      {rows.length > 0 ? (
        <section className="mt-8">
          <h2 className="t-footnote t-secondary uppercase tracking-wide">Products</h2>
          <ul className="mt-3 grid gap-4 sm:grid-cols-2">
            {rows.map(({ product, compliance }) => (
              <li key={product.id} className="card p-5" data-testid={`product-${product.id}`}>
                <Link href={`/products/${product.id}`} className="t-headline">
                  {product.name}
                </Link>
                <p className="t-footnote t-secondary mt-1">
                  {plain(product.product_type)} · {product.ingredients.length} ingredients
                </p>

                <div className="mt-4 space-y-2">
                  {compliance && Object.keys(compliance.statuses).length > 0 ? (
                    Object.entries(compliance.statuses).map(([marketId, status]) => (
                      <div key={marketId} className="flex items-center justify-between gap-3">
                        <span className="t-subhead">{marketName(marketId)}</span>
                        <StatusBadge status={status} testId={`status-${marketId}-${status}`} />
                      </div>
                    ))
                  ) : (
                    <p className="t-footnote t-secondary">
                      Not checked yet — add a regulation to start.
                    </p>
                  )}
                </div>

                <Link
                  href={`/products/${product.id}`}
                  className="btn btn-secondary btn-small mt-4"
                  data-testid={`open-${product.id}`}
                >
                  See the details
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {docs.length > 0 ? (
        <section className="mt-10">
          <div className="flex items-baseline justify-between">
            <h2 className="t-footnote t-secondary uppercase tracking-wide">Rules you have added</h2>
            <Link href="/documents/new" className="btn btn-quiet btn-small">Add another</Link>
          </div>
          <ul className="card mt-3 overflow-hidden">
            {docs.slice(0, 5).map((doc) => (
              <li key={doc.id} className="row">
                <Link href={`/documents/${doc.id}`} className="flex items-center justify-between gap-3 px-5 py-4">
                  <span className="min-w-0">
                    <span className="t-subhead block truncate">{doc.source_name}</span>
                    <span className="t-footnote t-secondary">
                      {jurisdictionName(doc.jurisdiction)}
                      {doc.filename ? ` · ${doc.filename}` : ""}
                    </span>
                  </span>
                  <span className="t-footnote t-secondary whitespace-nowrap">{plain(doc.status)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </main>
  );
}

/** First run only: the three steps, in order, with the door to step one open. */
function StartHere() {
  const steps = [
    {
      title: "Describe your product",
      body: "Name it, list what is inside it, and tick the countries you want to sell it in. Two minutes, no jargon.",
      href: "/products/new",
      cta: "Add a product",
    },
    {
      title: "Add the rules that apply",
      body: "Upload a regulation PDF, or paste text from an announcement. ReguLens reads it and pulls out the limits.",
      href: "/documents/new",
      cta: "Add rules",
    },
    {
      title: "Read the answer",
      body: "Each market shows whether your product is allowed. If a later rule changes that, you are told without asking.",
      href: null,
      cta: null,
    },
  ];

  return (
    <section className="card mt-8 p-6" data-testid="products-empty">
      <h2 className="t-title">Start here</h2>
      <p className="t-subhead t-secondary mt-1">Three steps. You only do the first two.</p>
      <ol className="mt-6 space-y-5">
        {steps.map((step, index) => (
          <li key={step.title} className="flex gap-4">
            <span
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full t-footnote"
              style={{ background: "var(--accent)", color: "var(--accent-ink)", fontWeight: 600 }}
              aria-hidden="true"
            >
              {index + 1}
            </span>
            <div>
              <p className="t-headline">{step.title}</p>
              <p className="t-subhead t-secondary mt-1">{step.body}</p>
              {step.href ? (
                <Link href={step.href} className="btn btn-secondary btn-small mt-3">
                  {step.cta}
                </Link>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
