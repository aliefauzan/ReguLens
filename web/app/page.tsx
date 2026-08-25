import Link from "next/link";
import {
  getCompliance,
  listClauses,
  listConflicts,
  listDocuments,
  listProducts,
  type ComplianceView,
  type Product,
} from "@/lib/api";
import AlertsBanner from "./AlertsBanner";
import { StatusBadge, marketName, jurisdictionName, plain } from "./_ui/status";

export const dynamic = "force-dynamic";

type Row = { product: Product; compliance: ComplianceView | null };

async function loadAll(): Promise<{
  rows: Row[];
  docs: Awaited<ReturnType<typeof listDocuments>>["documents"];
  toCheck: number;
  disagreements: number;
  error: string | null;
}> {
  try {
    const [{ products }, { documents }, toCheck, disagreements] = await Promise.all([
      listProducts(),
      listDocuments(),
      listClauses({ status: "needs_review" })
        .then((r) => r.clauses.length)
        .catch(() => 0),
      listConflicts()
        .then((r) => r.conflicts.length)
        .catch(() => 0),
    ]);
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
    return { rows, docs: documents, toCheck, disagreements, error: null };
  } catch {
    // An unreachable API and an empty account must never look the same.
    return {
      rows: [],
      docs: [],
      toCheck: 0,
      disagreements: 0,
      error:
        "We could not reach the ReguLens service. Check that it is running, then reload this page.",
    };
  }
}

type NextStep = { title: string; body: string; href: string; cta: string; tone: "act" | "calm" };

/**
 * The single most useful thing to do next, decided from the actual state.
 *
 * A dashboard that shows everything at once tells a first-time user nothing.
 * The order below is the order the work has to happen in: you cannot check a
 * product against rules you have not added, and a broken rule matters more
 * than a rule waiting to be confirmed.
 */
function nextStep(
  rows: Row[],
  docCount: number,
  toCheck: number,
  disagreements: number,
): NextStep | null {
  const broken = rows.filter(({ compliance }) =>
    Object.values(compliance?.statuses ?? {}).includes("non_compliant"),
  );
  if (broken.length > 0) {
    const product = broken[0].product;
    return {
      title:
        broken.length === 1
          ? `${product.name} breaks a rule`
          : `${broken.length} products break a rule`,
      body: "Open it to see which ingredient is over the limit, in which country, and by how much.",
      href: `/products/${product.id}`,
      cta: "See what is wrong",
      tone: "act",
    };
  }

  const unknown = rows.flatMap(({ product, compliance }) =>
    Object.entries(compliance?.statuses ?? {})
      .filter(([, status]) => status === "unknown")
      .map(([marketId]) => ({ product, marketId })),
  );
  if (docCount === 0 || unknown.length > 0) {
    const target = unknown[0];
    return {
      title: target
        ? `No rules added for ${marketName(target.marketId)} yet`
        : "Add the rules that apply to your products",
      body: "Until a regulation is added for a market, there is nothing to check against and we will not pretend otherwise.",
      href: "/documents/new",
      cta: "Add rules",
      tone: "act",
    };
  }

  if (toCheck > 0) {
    return {
      title: `${toCheck} rule${toCheck === 1 ? "" : "s"} waiting for you to check`,
      body: "These were not confident enough, or came from a source that cannot change anything on its own.",
      href: "/review",
      cta: "Check them",
      tone: "act",
    };
  }

  if (disagreements > 0) {
    return {
      title: `${disagreements} pair${disagreements === 1 ? "" : "s"} of rules disagree`,
      body: "Two countries allow different amounts. Following the stricter one keeps you legal in both.",
      href: "/conflicts",
      cta: "See the difference",
      tone: "calm",
    };
  }

  return {
    title: "Nothing needs your attention",
    body: "Every product passes in every market you have added rules for. If a new rule changes that, this page will say so on its own.",
    href: "/documents/new",
    cta: "Add more rules",
    tone: "calm",
  };
}

export default async function Home() {
  const { rows, docs, toCheck, disagreements, error } = await loadAll();
  const firstRun = rows.length === 0 && !error;
  const step = firstRun || error ? null : nextStep(rows, docs.length, toCheck, disagreements);

  return (
    <main className="mx-auto max-w-5xl px-5 py-8 sm:px-6 sm:py-12" data-testid="home">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="t-large-title">Your products</h1>
          <p className="t-body t-secondary prose-measure mt-2">
            Each product is checked against the rules of every market you sell into.
            When a new rule arrives, the answer here updates by itself.
          </p>
        </div>
        <Link href="/products/new" className="btn btn-primary" data-testid="new-product-link">
          Add a product
        </Link>
      </header>

      {step ? (
        <section
          className="card mt-6 p-6"
          style={{ borderLeft: `4px solid ${step.tone === "act" ? "var(--accent)" : "var(--good)"}` }}
          data-testid="next-step"
        >
          <p className="t-footnote t-secondary">What to do next</p>
          <h2 className="t-section mt-1">{step.title}</h2>
          <p className="t-footnote t-secondary prose-measure mt-2">{step.body}</p>
          <Link href={step.href} className="btn btn-primary btn-small mt-4" data-testid="next-step-cta">
            {step.cta}
          </Link>
        </section>
      ) : null}

      <AlertsBanner />

      {error ? (
        <div className="card mt-8 p-5" data-testid="products-error">
          <p className="t-headline" style={{ color: "var(--danger)" }}>Service unavailable</p>
          <p className="t-footnote t-secondary mt-1">{error}</p>
        </div>
      ) : null}

      {firstRun ? <StartHere /> : null}

      {rows.length > 0 ? (
        <section className="mt-8">
          <h2 className="t-section">Products</h2>
          <ul className="mt-4 grid gap-4">
            {rows.map(({ product, compliance }) => (
              <li key={product.id} className="card p-5" data-testid={`product-${product.id}`}>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <Link href={`/products/${product.id}`} className="t-headline">
                      {product.name}
                    </Link>
                    <p className="t-footnote t-secondary mt-1">
                      {plain(product.product_type)} · {product.ingredients.length} ingredients
                    </p>
                  </div>
                  <Link
                    href={`/products/${product.id}`}
                    className="btn btn-secondary btn-small"
                    data-testid={`open-${product.id}`}
                  >
                    See the details
                  </Link>
                </div>

                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  {compliance && Object.keys(compliance.statuses).length > 0 ? (
                    Object.entries(compliance.statuses).map(([marketId, status]) => (
                      <div key={marketId} className="inset flex items-center justify-between gap-3 p-4">
                        <span className="t-body">{marketName(marketId)}</span>
                        <StatusBadge status={status} testId={`status-${marketId}-${status}`} />
                      </div>
                    ))
                  ) : (
                    <p className="t-footnote t-secondary">
                      Not checked yet — add a regulation to start.
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {docs.length > 0 ? (
        <section className="mt-10">
          <div className="flex items-baseline justify-between">
            <h2 className="t-section">Rules you have added</h2>
            <Link href="/documents/new" className="btn btn-quiet btn-small">Add another</Link>
          </div>
          <ul className="card mt-4 overflow-hidden">
            {docs.slice(0, 5).map((doc) => (
              <li key={doc.id} className="row">
                <Link href={`/documents/${doc.id}`} className="flex items-center justify-between gap-3 px-5 py-4">
                  <span className="min-w-0">
                    <span className="t-body block truncate">{doc.source_name}</span>
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
      <p className="t-body t-secondary mt-2">Three steps. You only do the first two.</p>
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
              <p className="t-footnote t-secondary prose-measure mt-1">{step.body}</p>
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
