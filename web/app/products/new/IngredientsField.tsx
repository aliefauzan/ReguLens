"use client";

import { useEffect, useMemo, useState } from "react";
import { listSubstances, UNITS, type Substance } from "@/lib/api";
import { parseIngredientList } from "@/lib/ingredients";
import { plain } from "../../_ui/status";

export type Row = { name: string; amount: string; unit: string; note?: string };

export const EMPTY_ROW: Row = { name: "", amount: "", unit: "" };

/**
 * Two ways in, because two kinds of user turn up.
 *
 * Typing ingredients one at a time is fine for somebody who knows their recipe
 * and is willing. Most people have the list already printed on the packaging,
 * so the default is to paste it and correct what we read. Nothing is inferred
 * silently: every parsed row lands in the same editable table, and a number we
 * could not attach a unit to says so on the row instead of being dropped or
 * guessed at.
 */
export default function IngredientsField({
  rows,
  setRows,
}: {
  rows: Row[];
  setRows: (next: Row[] | ((current: Row[]) => Row[])) => void;
}) {
  const [mode, setMode] = useState<"paste" | "list">("paste");
  const [pasted, setPasted] = useState("");
  const [readCount, setReadCount] = useState<number | null>(null);
  const [substances, setSubstances] = useState<Substance[]>([]);

  useEffect(() => {
    // Offering the names that can actually match a clause is the cheapest way
    // to avoid an unrecognised ingredient reading as "no problems found".
    listSubstances()
      .then((data) => setSubstances(data.substances))
      .catch(() => setSubstances([]));
  }, []);

  const suggestions = useMemo(() => {
    const names = new Set<string>();
    for (const substance of substances) {
      names.add(substance.label);
      // E-numbers are what appears on European packaging.
      for (const synonym of substance.synonyms) {
        if (/^e ?\d{3}$/i.test(synonym)) names.add(synonym.toUpperCase().replace(" ", ""));
      }
    }
    return [...names].sort();
  }, [substances]);

  function readPastedList() {
    const parsed = parseIngredientList(pasted);
    setReadCount(parsed.length);
    if (parsed.length === 0) return;
    setRows(parsed);
    setMode("list");
  }

  function updateRow(index: number, patch: Partial<Row>) {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function removeRow(index: number) {
    setRows((current) => (current.length === 1 ? current : current.filter((_, i) => i !== index)));
  }

  return (
    <fieldset className="card p-6" data-testid="field-ingredients">
      <legend className="t-section float-left w-full">What is inside it?</legend>
      <p className="help clear-both prose-measure">
        Only preservatives and additives need an amount — that is what gets compared against the
        legal limit. Everything else can be a name on its own, and an amount you are unsure of is
        better left blank than guessed.
      </p>

      <div className="mt-4 flex gap-2">
        <button
          type="button"
          className={mode === "paste" ? "btn btn-primary btn-small" : "btn btn-secondary btn-small"}
          onClick={() => setMode("paste")}
          data-testid="mode-paste"
        >
          Paste the list
        </button>
        <button
          type="button"
          className={mode === "list" ? "btn btn-primary btn-small" : "btn btn-secondary btn-small"}
          onClick={() => setMode("list")}
          data-testid="mode-list"
        >
          Enter one by one
        </button>
      </div>

      {mode === "paste" ? (
        <div className="mt-4">
          <label className="block">
            <span className="label">Copy the ingredients straight off your packaging</span>
            <textarea
              className="field"
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
              placeholder={"Ingredients: ginger, turmeric, honey powder, sodium benzoate (0.08%)"}
              data-testid="ingredients-paste"
            />
            <span className="help">
              Commas or new lines both work. We will show you what we read so you can fix it before
              anything is saved.
            </span>
          </label>
          <button
            type="button"
            className="btn btn-primary btn-small mt-3"
            onClick={readPastedList}
            disabled={!pasted.trim()}
            data-testid="read-ingredients"
          >
            Read this list
          </button>
          {readCount === 0 ? (
            <p className="t-footnote mt-3" style={{ color: "var(--warn)" }}>
              We could not pick any ingredients out of that. Try one per line, or enter them one by
              one.
            </p>
          ) : null}
        </div>
      ) : (
        <div className="mt-4">
          {readCount !== null && readCount > 0 ? (
            <p className="t-footnote t-secondary mb-3" data-testid="parse-summary">
              We read {readCount} ingredient{readCount === 1 ? "" : "s"}. Check the amounts — we only
              fill one in when the text was unambiguous.
            </p>
          ) : null}

          <datalist id="substance-suggestions">
            {suggestions.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>

          <div className="space-y-3">
            {rows.map((row, index) => (
              <div key={index} className="inset p-4">
                <div className="grid gap-3 sm:grid-cols-[1fr_7rem_11rem_auto]">
                  <label className="block">
                    <span className="label sm:sr-only">Ingredient</span>
                    <input
                      className="field"
                      list="substance-suggestions"
                      placeholder="e.g. sodium benzoate, or E211"
                      value={row.name}
                      onChange={(e) => updateRow(index, { name: e.target.value })}
                      data-testid={`ingredient-name-${index}`}
                    />
                  </label>
                  <label className="block">
                    <span className="label sm:sr-only">Amount</span>
                    <input
                      className="field"
                      placeholder="amount"
                      inputMode="decimal"
                      value={row.amount}
                      onChange={(e) => updateRow(index, { amount: e.target.value })}
                      data-testid={`ingredient-amount-${index}`}
                    />
                  </label>
                  <label className="block">
                    <span className="label sm:sr-only">Unit</span>
                    <select
                      className="field"
                      value={row.unit}
                      onChange={(e) => updateRow(index, { unit: e.target.value })}
                      data-testid={`ingredient-unit-${index}`}
                    >
                      <option value="">unit…</option>
                      {UNITS.map((unit) => (
                        <option key={unit} value={unit}>
                          {plain(unit)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    className="btn btn-quiet btn-small"
                    onClick={() => removeRow(index)}
                    aria-label={`Remove ingredient ${index + 1}`}
                    disabled={rows.length === 1}
                  >
                    Remove
                  </button>
                </div>

                {row.note ? (
                  <p className="t-footnote mt-2" style={{ color: "var(--warn)" }}>
                    {row.note}
                  </p>
                ) : null}
                {row.amount.trim() && !row.unit ? (
                  <p className="t-footnote mt-2" style={{ color: "var(--warn)" }}>
                    Pick a unit, or clear the amount — a number on its own cannot be compared with a
                    legal limit.
                  </p>
                ) : null}
              </div>
            ))}
          </div>

          <button
            type="button"
            className="btn btn-secondary btn-small mt-4"
            onClick={() => setRows((current) => [...current, { ...EMPTY_ROW }])}
            data-testid="add-ingredient"
          >
            Add another ingredient
          </button>
        </div>
      )}
    </fieldset>
  );
}
