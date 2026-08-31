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
import GetStarted, { type Progress } from "./GetStarted";
import Icon from "./_ui/Icon";
import {
  StatusBadge,
  marketName,
  marketShortName,
  jurisdictionName,
  plain,
  statusCopy,
} from "./_ui/status";

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
      body: "Drop in the document; we work out which country it applies to. Until a regulation is added for a market, there is nothing to check against and we will not pretend otherwise.",
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

/**
 * How far through the three opening steps this workspace is.
 *
 * Read from real state, never from a flag: a step counts as done when the
 * thing it produces exists. "Rules added" therefore means a document that
 * finished extraction — one still being read has not yet told anyone anything.
 */
function progressOf(rows: Row[], docs: Awaited<ReturnType<typeof listDocuments>>["documents"]): Progress {
  return {
    product: rows.length > 0,
    rules: docs.some((doc) => doc.status === "extracted" || doc.status === "reconciled"),
    answer: rows.some(({ compliance }) =>
      Object.values(compliance?.statuses ?? {}).some((status) => status !== "unknown"),
    ),
  };
}

/** The four numbers the strip reports, counted from the rows the table shows. */
function summarise(rows: Row[], toCheck: number, disagreements: number) {
  const verdicts = rows.flatMap(({ compliance }) => Object.entries(compliance?.statuses ?? {}));
  const markets = new Set(verdicts.map(([marketId]) => marketId));
  return {
    products: rows.length,
    markets: markets.size,
    breaking: verdicts.filter(([, status]) => status === "non_compliant").length,
    queue: toCheck + disagreements,
  };
}

/** A metric reads as one thing: the number, then what it counts. */
function Kpi({
  label,
  value,
  note,
  href,
  tone,
  testId,
}: {
  label: string;
  value: number | string;
  note: string;
  href: string;
  tone?: "danger" | "warn";
  testId: string;
}) {
  return (
    <Link href={href} className="kpi" data-testid={testId}>
      <span className="t-eyebrow">{label}</span>
      <span
        className="t-number mt-2 block"
        style={
          tone === "danger"
            ? { color: "var(--danger)" }
            : tone === "warn"
              ? { color: "var(--warn)" }
              : undefined
        }
      >
        {value}
      </span>
      <span className="t-caption mt-1 block">{note}</span>
    </Link>
  );
}

export default async function Home() {
  const { rows, docs, toCheck, disagreements, error } = await loadAll();
  const progress = progressOf(rows, docs);
  const onboarding = !error && !(progress.product && progress.rules && progress.answer);
  // While the checklist is up it *is* the next step; two cards competing to say
  // what to do next is worse than either alone.
  const step = onboarding || error ? null : nextStep(rows, docs.length, toCheck, disagreements);
  const totals = summarise(rows, toCheck, disagreements);

  return (
    <main className="page" data-testid="home">
      <header>
        <h1 className="t-large-title">Overview</h1>
        <p className="t-footnote t-secondary prose-measure mt-1.5">
          Every product, checked against the rules of every market you sell into. When a new
          rule arrives, the answer here updates by itself.
        </p>
      </header>

      {error ? (
        <div className="card mt-5 p-5" data-testid="products-error">
          <p className="t-headline" style={{ color: "var(--danger)" }}>Service unavailable</p>
          <p className="t-footnote t-secondary mt-1">{error}</p>
        </div>
      ) : (
        <section className="kpi-strip rise mt-5" data-testid="kpi-strip">
          <Kpi
            label="Products"
            value={totals.products}
            note="being tracked"
            href="/"
            testId="kpi-products"
          />
          <Kpi
            label="Markets"
            value={totals.markets}
            note="with a verdict"
            href="/rules"
            testId="kpi-markets"
          />
          <Kpi
            label="Breaking a rule"
            value={totals.breaking}
            note={totals.breaking === 0 ? "nothing over a limit" : "product / market pairs"}
            href="/conflicts"
            tone={totals.breaking > 0 ? "danger" : undefined}
            testId="kpi-breaking"
          />
          <Kpi
            label="Waiting on you"
            value={totals.queue}
            note={`${toCheck} to check · ${disagreements} disagree`}
            href="/review"
            tone={totals.queue > 0 ? "warn" : undefined}
            testId="kpi-queue"
          />
        </section>
      )}

      {/* Asymmetric on purpose: the verdict table is the work, the right-hand
          column is everything that is only worth a glance. */}
      <div className="mt-5 grid items-start gap-5 xl:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <div className="grid gap-5">
          {onboarding ? <GetStarted progress={progress} /> : null}

          {rows.length > 0 ? (
            <section
              className="panel rise overflow-hidden"
              style={{ "--i": 1 } as React.CSSProperties}
              data-testid="products-panel"
            >
              <div className="panel-head">
                <h2 className="t-section">Verdict by market</h2>
                <span className="t-caption">
                  {rows.length} {rows.length === 1 ? "product" : "products"}
                </span>
              </div>
              <ul>
                {rows.map(({ product, compliance }, index) => {
                  const statuses = Object.entries(compliance?.statuses ?? {});
                  const worst = statuses.some(([, s]) => s === "non_compliant")
                    ? "var(--danger)"
                    : statuses.some(([, s]) => s === "attention_required")
                      ? "var(--warn)"
                      : statuses.some(([, s]) => s === "compliant")
                        ? "var(--good)"
                        : "var(--separator-strong)";
                  return (
                    <li
                      key={product.id}
                      className="row row-hover rise"
                      style={{ "--i": index + 2 } as React.CSSProperties}
                      data-testid={`product-${product.id}`}
                    >
                      <div className="grid items-center gap-x-4 gap-y-2 px-4 py-3.5 sm:px-5 md:grid-cols-[3px_minmax(240px,1fr)_auto_auto]">
                        {/* A 3px bar carries the worst verdict for the row, so a
                            long list can be triaged before reading a word. */}
                        <span
                          aria-hidden="true"
                          className="hidden h-8 w-[3px] rounded-full md:block"
                          style={{ background: worst }}
                        />
                        <div className="min-w-0">
                          <Link href={`/products/${product.id}`} className="t-headline block truncate">
                            {product.name}
                          </Link>
                          <p className="t-caption mt-0.5 truncate">
                            {plain(product.product_type)} ·{" "}
                            <span className="mono">{product.ingredients.length}</span>{" "}
                            {product.ingredients.length === 1 ? "ingredient" : "ingredients"}
                          </p>
                        </div>

                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 md:justify-end">
                          {statuses.length > 0 ? (
                            statuses.map(([marketId, status]) => (
                              <span key={marketId} className="flex items-center gap-1.5">
                                <span className="t-caption whitespace-nowrap" title={marketName(marketId)}>
                                  {marketShortName(marketId)}
                                </span>
                                <StatusBadge status={status} testId={`status-${marketId}-${status}`} />
                              </span>
                            ))
                          ) : (
                            <span className="t-caption">Not checked yet — add a regulation to start.</span>
                          )}
                        </div>

                        <Link
                          href={`/products/${product.id}`}
                          className="btn btn-quiet btn-small justify-self-start md:justify-self-end"
                          data-testid={`open-${product.id}`}
                        >
                          Details
                          <Icon name="arrow" size={15} />
                        </Link>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          ) : null}

          {docs.length > 0 ? (
            <section className="panel rise overflow-hidden" style={{ "--i": 2 } as React.CSSProperties}>
              <div className="panel-head">
                <h2 className="t-section">Rules ReguLens has read</h2>
                <div className="flex gap-1">
                  <Link href="/rules" className="btn btn-quiet btn-small" data-testid="see-all-rules">
                    See every rule
                  </Link>
                  <Link href="/documents/new" className="btn btn-quiet btn-small">Add another</Link>
                </div>
              </div>
              <ul>
                {docs.slice(0, 6).map((doc) => (
                  <li key={doc.id} className="row row-hover">
                    <Link
                      href={`/documents/${doc.id}`}
                      className="flex items-center justify-between gap-3 px-4 py-3 sm:px-5"
                    >
                      <span className="min-w-0">
                        <span className="t-subhead block truncate">{doc.source_name}</span>
                        <span className="t-caption">
                          {jurisdictionName(doc.jurisdiction)}
                          {/* Pasted text gets a generated `doc_x.txt` name that means
                              nothing to anyone; only a real uploaded file is worth
                              naming. A rulebook entry was not pasted by anybody, and
                              saying so would make the reader wonder who did. */}
                          {doc.origin === "library"
                            ? " · from the built-in rules"
                            : doc.filename && !/^doc_[a-z0-9]+\.txt$/.test(doc.filename)
                              ? ` · ${doc.filename}`
                              : " · pasted text"}
                        </span>
                      </span>
                      <span className="t-caption whitespace-nowrap">{plain(doc.status)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>

        {/* Right column: what to do, and what happened while you were away. */}
        <div className="grid gap-5">
          {step ? (
            <section
              className="panel rise p-5"
              style={
                {
                  "--i": 1,
                  borderTop: `3px solid ${step.tone === "act" ? "var(--accent)" : "var(--good)"}`,
                } as React.CSSProperties
              }
              data-testid="next-step"
            >
              <p className="t-eyebrow">What to do next</p>
              <h2 className="t-title mt-2">{step.title}</h2>
              <p className="t-footnote t-secondary mt-2">{step.body}</p>
              <Link href={step.href} className="btn btn-primary btn-small mt-4" data-testid="next-step-cta">
                {step.cta}
              </Link>
            </section>
          ) : null}

          <AlertsBanner />

          {!error && rows.length > 0 ? (
            <section className="panel rise p-5" style={{ "--i": 3 } as React.CSSProperties}>
              <p className="t-eyebrow">How a verdict is read</p>
              <ul className="mt-3 grid gap-2.5">
                {(["compliant", "non_compliant", "attention_required", "unknown"] as const).map((status) => (
                  <li key={status} className="flex items-start gap-2.5">
                    <StatusBadge status={status} testId={`legend-${status}`} />
                    <span className="t-caption pt-1">{statusCopy(status).meaning}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      </div>
    </main>
  );
}
