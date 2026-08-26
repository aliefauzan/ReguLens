"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { seedDemo } from "@/lib/api";

/**
 * The three steps, kept on screen until all three are done.
 *
 * The earlier version of this only appeared when the workspace was completely
 * empty, so it vanished the moment a product existed — taking the knowledge
 * that step two exists with it. A checklist that disappears halfway is how
 * people end up asking a human what to do next.
 */
export type Progress = { product: boolean; rules: boolean; answer: boolean };

const STEPS: { key: keyof Progress; title: string; body: string; href: string | null; cta: string | null }[] = [
  {
    key: "product",
    title: "Describe your product",
    body: "Name it, list what is inside it, and tick the countries you want to sell it in. Two minutes, no jargon.",
    href: "/products/new",
    cta: "Add a product",
  },
  {
    key: "rules",
    title: "Add the rules that apply",
    body: "Upload a regulation PDF, paste text from an announcement, or start from one of the bundled samples.",
    href: "/documents/new",
    cta: "Add rules",
  },
  {
    key: "answer",
    title: "Read the answer",
    body: "Each market shows whether your product is allowed. If a later rule changes that, you are told without asking.",
    href: null,
    cta: null,
  },
];

export default function GetStarted({ progress }: { progress: Progress }) {
  const router = useRouter();
  const [seeding, setSeeding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const current = STEPS.findIndex((step) => !progress[step.key]);
  const empty = !progress.product;

  async function loadSample() {
    setError(null);
    setSeeding(true);
    try {
      const { product, document, cached } = await seedDemo();
      // A freshly ingested rule is still being read. Landing on the product
      // would show "no rules added yet" for as long as extraction takes, which
      // reads as a broken button; the document page shows the work happening.
      router.push(cached ? `/products/${product.id}` : `/documents/${document.id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The sample data did not load.");
      setSeeding(false);
    }
  }

  return (
    <section className="card mt-8 p-6" data-testid="get-started">
      <h2 className="t-title">{empty ? "Start here" : "Getting started"}</h2>
      <p className="t-body t-secondary mt-2">
        Three steps. You only do the first two.
      </p>

      <ol className="mt-6 space-y-5">
        {STEPS.map((step, index) => {
          const done = progress[step.key];
          const active = index === current;
          return (
            <li key={step.key} className="flex gap-4" data-testid={`step-${step.key}-${done ? "done" : "todo"}`}>
              <span
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full t-footnote"
                style={{
                  background: done ? "var(--good)" : active ? "var(--accent)" : "var(--fill)",
                  color: done || active ? "var(--accent-ink)" : "var(--secondary)",
                  fontWeight: 600,
                }}
                aria-hidden="true"
              >
                {done ? "✓" : index + 1}
              </span>
              <div>
                <p className="t-headline" style={{ color: done ? "var(--secondary)" : undefined }}>
                  {step.title}
                  {done ? <span className="t-footnote t-secondary"> · done</span> : null}
                </p>
                <p className="t-footnote t-secondary prose-measure mt-1">{step.body}</p>
                {step.href && !done ? (
                  <Link
                    href={step.href}
                    className={`btn btn-small mt-3 ${active ? "btn-primary" : "btn-secondary"}`}
                    data-testid={`step-cta-${step.key}`}
                  >
                    {step.cta}
                  </Link>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>

      {empty ? (
        // Someone judging the app in five minutes has no regulation PDF on
        // their desk. Without this, step two is a wall.
        <div className="inset mt-6 p-5">
          <p className="t-headline">No product of your own to hand?</p>
          <p className="t-footnote t-secondary prose-measure mt-1">
            Load a demo drink powder and one real Indonesian rule for it, then add the EU rule
            yourself to watch the verdict change. Uses the same pipeline as your own uploads.
          </p>
          <button
            type="button"
            className="btn btn-secondary btn-small mt-3"
            onClick={loadSample}
            disabled={seeding}
            data-testid="seed-demo"
          >
            {seeding ? "Loading…" : "Try it with sample data"}
          </button>
          {error ? (
            <p className="t-footnote mt-2" style={{ color: "var(--danger)" }} data-testid="seed-demo-error">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
