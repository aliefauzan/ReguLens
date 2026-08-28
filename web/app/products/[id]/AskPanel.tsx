"use client";

import { useState } from "react";
import { ask, type QueryResult } from "@/lib/api";
import { jurisdictionName, marketName } from "../../_ui/status";

/**
 * Suggested questions built from this product's own state.
 *
 * The fixed list asked "Can I sell this in Germany?" on products that do not
 * go to Germany, which teaches a first-time user the wrong model of what the
 * app knows. Every suggestion here is about a market this product actually
 * targets, and the failing one leads.
 */
function suggestionsFor(name: string, failingMarket: string | null, markets: string[]): string[] {
  const out: string[] = [];
  if (failingMarket) out.push(`Why does ${name} break the rules in ${marketName(failingMarket)}?`);
  for (const marketId of markets) {
    if (marketId !== failingMarket) out.push(`Can I sell ${name} in ${marketName(marketId)}?`);
  }
  out.push(`What rules apply to ${name}?`);
  return out.slice(0, 3);
}

export default function AskPanel({
  productId,
  productName,
  failingMarket,
  markets,
}: {
  productId: string;
  productName: string;
  failingMarket: string | null;
  markets: string[];
}) {
  const SUGGESTIONS = suggestionsFor(productName, failingMarket, markets);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(q: string) {
    setError(null);
    setLoading(true);
    setResult(null);
    try {
      setResult(await ask(q, productId));
    } catch {
      setError("We could not reach the ReguLens service. Check that it is running, then try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card mt-10 p-6" data-testid="ask-panel">
      <h2 className="t-section">Ask a question</h2>
      <p className="t-footnote t-secondary prose-measure mt-2">
        Plain English is fine. Every answer quotes the exact rule it came from — and if no rule covers
        your question, it says so instead of guessing.
      </p>

      <form
        className="mt-4 flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim()) submit(question.trim());
        }}
      >
        <input
          className="field flex-1"
          placeholder={SUGGESTIONS[0]}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          data-testid="ask-input"
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="btn btn-primary"
          data-testid="ask-submit"
        >
          {loading ? "Asking…" : "Ask"}
        </button>
      </form>

      <div className="mt-3 flex flex-wrap gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            className="btn btn-secondary btn-small"
            onClick={() => {
              setQuestion(s);
              submit(s);
            }}
            data-testid={`suggest-${s.slice(0, 12).replaceAll(" ", "-")}`}
          >
            {s}
          </button>
        ))}
      </div>

      {error ? (
        <p className="t-subhead mt-4" style={{ color: "var(--danger)" }} data-testid="ask-error">
          {error}
        </p>
      ) : null}

      {result ? (
        <div className="inset mt-5 p-5" data-testid="answer-card">
          <p className="t-body" data-testid="answer-text">{result.answer}</p>

          {result.refusal ? (
            <p className="badge badge-muted mt-3" data-testid="refusal-flag">
              No rule in your data answers this — nothing was invented
            </p>
          ) : null}

          {result.cited_clauses.length > 0 ? (
            <div className="mt-4" data-testid="citations">
              <p className="t-headline">Based on these rules</p>
              <div className="mt-2 space-y-2">
                {result.cited_clauses.map((clause) => (
                  <div
                    key={clause.id}
                    className="p-4"
                    style={{ background: "var(--surface)", borderRadius: "var(--radius-control)" }}
                    data-testid={`citation-${clause.id}`}
                  >
                    <p className="t-footnote t-secondary">{jurisdictionName(clause.jurisdiction)}</p>
                    <p className="t-body mt-1">{clause.text}</p>
                    <p className="t-caption mono mt-2">{clause.id}</p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <p className="t-caption t-secondary mt-4">
            {result.confidence !== null ? `Confidence ${Math.round(result.confidence * 100)}%` : "Confidence —"} ·
            answered in {result.latency_ms} ms
          </p>
        </div>
      ) : null}
    </section>
  );
}
