"use client";

import { useState } from "react";
import { ask, type QueryResult } from "@/lib/api";
import { jurisdictionName } from "../../_ui/status";

const SUGGESTIONS = [
  "Why is my product at risk?",
  "What changed in the EU rules?",
  "Can I sell this in Germany?",
];

export default function AskPanel({ productId }: { productId: string }) {
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
      <h2 className="t-headline">Ask a question</h2>
      <p className="t-subhead t-secondary mt-1">
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
          placeholder="Why is my product at risk?"
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
          <p className="t-subhead" data-testid="answer-text">{result.answer}</p>

          {result.refusal ? (
            <p className="badge badge-muted mt-3" data-testid="refusal-flag">
              No rule in your data answers this — nothing was invented
            </p>
          ) : null}

          {result.cited_clauses.length > 0 ? (
            <div className="mt-4" data-testid="citations">
              <p className="t-footnote t-secondary uppercase tracking-wide">Based on these rules</p>
              <div className="mt-2 space-y-2">
                {result.cited_clauses.map((clause) => (
                  <div
                    key={clause.id}
                    className="p-4"
                    style={{ background: "var(--surface)", borderRadius: "var(--radius-control)" }}
                    data-testid={`citation-${clause.id}`}
                  >
                    <p className="t-footnote t-secondary">{jurisdictionName(clause.jurisdiction)}</p>
                    <p className="t-subhead mt-1">{clause.text}</p>
                    <p className="t-caption t-secondary mono mt-2">{clause.id}</p>
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
