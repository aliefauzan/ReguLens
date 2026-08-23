"use client";

import { useState } from "react";
import { ask, type QueryResult } from "@/lib/api";

const SUGGESTIONS = [
  "Why is my product at risk?",
  "What changed in the EU regulation?",
  "Can I export to Germany?",
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
      setError("Could not reach the API.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="mt-10" data-testid="ask-panel">
      <h2 className="text-sm font-medium uppercase tracking-wide opacity-60">Ask</h2>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim()) submit(question.trim());
        }}
      >
        <input
          className="flex-1 rounded-[8px] border bg-transparent p-2 text-sm"
          placeholder="Why is my product at risk?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          data-testid="ask-input"
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="rounded-full bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          data-testid="ask-submit"
        >
          {loading ? "Asking…" : "Ask"}
        </button>
      </form>
      <div className="mt-2 flex flex-wrap gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            className="rounded-full border px-3 py-1 text-xs opacity-70 hover:opacity-100"
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
        <p className="mt-3 text-sm" style={{ color: "var(--danger)" }} data-testid="ask-error">
          {error}
        </p>
      ) : null}

      {result ? (
        <div className="card mt-4 p-4" data-testid="answer-card">
          <p className="text-sm" data-testid="answer-text">{result.answer}</p>
          <div className="mt-2 flex items-center gap-3 text-xs opacity-60">
            <span>confidence: {result.confidence !== null ? Math.round(result.confidence * 100) + "%" : "—"}</span>
            <span>{result.latency_ms} ms</span>
            {result.refusal ? <span data-testid="refusal-flag">refused: no supporting data</span> : null}
          </div>
          {result.cited_clauses.length > 0 ? (
            <div className="mt-3 space-y-2" data-testid="citations">
              {result.cited_clauses.map((clause) => (
                <div key={clause.id} className="rounded-[8px] border p-3 text-xs" data-testid={`citation-${clause.id}`}>
                  <span className="font-mono opacity-60">{clause.id}</span>{" "}
                  <span className="opacity-70">({clause.jurisdiction})</span>
                  <p className="mt-1">{clause.text}</p>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
