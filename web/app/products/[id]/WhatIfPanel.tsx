"use client";

import { useState } from "react";
import { simulate, type SimulationResult } from "@/lib/api";
import { marketName, statusCopy } from "../../_ui/status";

/**
 * What-if, without saving anything.
 *
 * Answering "what if we cut it to 120 mg/kg" used to mean creating a real
 * product, waiting for the pipeline, reading the answer and deleting it again —
 * three of those four steps being things nobody wanted to do. The endpoint
 * behind this writes no document, emits no event and leaves no requirement row,
 * so it can be asked as often as somebody changes their mind.
 *
 * It shares its evaluator with the page above it. A preview that decided which
 * rules apply by its own route would eventually disagree with the verdict it is
 * previewing, and a disagreeing preview is worse than none.
 */
export default function WhatIfPanel({
  product,
}: {
  product: {
    name: string;
    product_type: string;
    origin: string;
    packaging?: string | null;
    target_markets: string[];
    ingredients: { name: string; amount?: number | null; unit?: string | null }[];
  };
}) {
  const measured = product.ingredients.filter((i) => i.amount != null);
  const [index, setIndex] = useState(0);
  const [amount, setAmount] = useState<string>(
    measured.length ? String(measured[0].amount) : "",
  );
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (measured.length === 0) return null;

  const chosen = measured[index];

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const next = product.ingredients.map((ingredient) =>
        ingredient === chosen ? { ...ingredient, amount: Number(amount) } : ingredient,
      );
      setResult(
        await simulate({
          name: product.name,
          product_type: product.product_type,
          origin: product.origin,
          packaging: product.packaging ?? null,
          target_markets: product.target_markets,
          ingredients: next.map((i) => ({
            name: i.name,
            amount: i.amount ?? null,
            unit: i.unit ?? null,
          })),
        }),
      );
    } catch {
      setError("The check could not be run just now. Nothing was changed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card mt-10 p-6" data-testid="what-if-panel">
      <h2 className="t-section">What if you changed the recipe?</h2>
      <p className="t-subhead t-secondary mt-2">
        Try a different amount and see the verdict before you commit to it. Nothing
        here is saved — your product is not changed by asking.
      </p>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="t-footnote t-secondary block">Ingredient</span>
          <select
            className="input mt-1"
            value={index}
            onChange={(event) => {
              const next = Number(event.target.value);
              setIndex(next);
              setAmount(String(measured[next].amount));
              setResult(null);
            }}
            data-testid="what-if-ingredient"
          >
            {measured.map((ingredient, i) => (
              <option key={ingredient.name} value={i}>
                {ingredient.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="t-footnote t-secondary block">New amount ({chosen.unit})</span>
          <input
            className="input mt-1"
            type="number"
            min="0"
            step="any"
            value={amount}
            onChange={(event) => {
              setAmount(event.target.value);
              setResult(null);
            }}
            data-testid="what-if-amount"
          />
        </label>
        <button
          className="btn btn-primary"
          onClick={run}
          disabled={busy || amount === ""}
          data-testid="what-if-run"
        >
          {busy ? "Checking…" : "Check it"}
        </button>
      </div>

      {error ? (
        <p className="t-footnote mt-3" style={{ color: "var(--danger)" }}>
          {error}
        </p>
      ) : null}

      {result ? (
        <div className="inset mt-5 p-5" data-testid="what-if-result">
          <p className="t-footnote t-secondary">
            If {chosen.name} were {amount} {chosen.unit} — not saved
          </p>
          <ul className="mt-3 space-y-2">
            {Object.entries(result.statuses).map(([marketId, status]) => (
              <li key={marketId} className="t-body">
                <strong>{marketName(marketId)}</strong>:{" "}
                <span
                  style={{
                    color:
                      status === "non_compliant"
                        ? "var(--danger)"
                        : status === "compliant"
                          ? "var(--good)"
                          : "var(--warn)",
                    fontWeight: 600,
                  }}
                >
                  {statusCopy(status).label.toLowerCase()}
                </span>
              </li>
            ))}
          </ul>
          {result.binding_limits.substances.length > 0 ? (
            <p className="t-footnote t-secondary mt-3">
              To sell in every market you target, the ceiling is{" "}
              {result.binding_limits.substances
                .map(
                  (s) =>
                    `${s.substance_normalized.replaceAll("_", " ")} ≤ ${s.binding_limit} mg/kg`,
                )
                .join(", ")}
              .
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
