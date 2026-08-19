"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createProduct, PRODUCT_TYPES, UNITS } from "@/lib/api";

type Row = { name: string; amount: string; unit: string };

const EMPTY_ROW: Row = { name: "", amount: "", unit: "" };

export default function ProductForm() {
  const router = useRouter();
  const [name, setName] = useState("Herbal Drink Powder");
  const [productType, setProductType] = useState<string>(PRODUCT_TYPES[0]);
  const [origin, setOrigin] = useState("ID");
  const [packaging, setPackaging] = useState("250g plastic pouch");
  const [markets, setMarkets] = useState<string[]>(["market_de"]);
  const [rows, setRows] = useState<Row[]>([
    { name: "ginger", amount: "", unit: "" },
    { name: "sodium benzoate", amount: "0.08", unit: "percent_w_w" },
  ]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function updateRow(index: number, patch: Partial<Row>) {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function toggleMarket(id: string) {
    setMarkets((current) =>
      current.includes(id) ? current.filter((m) => m !== id) : [...current, id],
    );
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const ingredients = rows
        .filter((row) => row.name.trim())
        .map((row) => ({
          name: row.name.trim(),
          // Send the unit only alongside an amount; the API rejects an amount
          // without one, and that rejection is the point.
          ...(row.amount.trim()
            ? { amount: Number(row.amount), unit: row.unit || null }
            : {}),
        }));
      const product = await createProduct({
        name,
        product_type: productType,
        origin,
        packaging: packaging || null,
        target_markets: markets,
        ingredients,
      });
      router.push(`/products/${product.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setSaving(false);
    }
  }

  return (
    <form className="mt-8 space-y-6" onSubmit={submit} data-testid="product-form">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="text-sm">Name</span>
          <input
            className="mt-1 w-full rounded border bg-transparent p-2"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            data-testid="field-name"
          />
        </label>

        <label className="block">
          <span className="text-sm">Product type</span>
          <select
            className="mt-1 w-full rounded border bg-transparent p-2"
            value={productType}
            onChange={(e) => setProductType(e.target.value)}
            data-testid="field-product-type"
          >
            {PRODUCT_TYPES.map((type) => (
              <option key={type} value={type}>
                {type.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="text-sm">Origin (ISO country code)</span>
          <input
            className="mt-1 w-full rounded border bg-transparent p-2"
            value={origin}
            maxLength={2}
            onChange={(e) => setOrigin(e.target.value.toUpperCase())}
            required
            data-testid="field-origin"
          />
        </label>

        <label className="block">
          <span className="text-sm">Packaging</span>
          <input
            className="mt-1 w-full rounded border bg-transparent p-2"
            value={packaging}
            onChange={(e) => setPackaging(e.target.value)}
            data-testid="field-packaging"
          />
        </label>
      </div>

      <fieldset data-testid="field-markets">
        <legend className="text-sm">Destination markets</legend>
        <div className="mt-2 flex gap-4">
          {[
            { id: "market_de", label: "Germany (EU)" },
            { id: "market_id", label: "Indonesia (BPOM)" },
          ].map((market) => (
            <label key={market.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={markets.includes(market.id)}
                onChange={() => toggleMarket(market.id)}
                data-testid={`market-${market.id}`}
              />
              {market.label}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset data-testid="field-ingredients">
        <legend className="text-sm">Ingredients</legend>
        <div className="mt-2 space-y-2">
          {rows.map((row, index) => (
            <div key={index} className="grid grid-cols-[1fr_6rem_9rem] gap-2">
              <input
                className="rounded border bg-transparent p-2"
                placeholder="name, e.g. sodium benzoate or E211"
                value={row.name}
                onChange={(e) => updateRow(index, { name: e.target.value })}
                data-testid={`ingredient-name-${index}`}
              />
              <input
                className="rounded border bg-transparent p-2"
                placeholder="amount"
                inputMode="decimal"
                value={row.amount}
                onChange={(e) => updateRow(index, { amount: e.target.value })}
                data-testid={`ingredient-amount-${index}`}
              />
              <select
                className="rounded border bg-transparent p-2"
                value={row.unit}
                onChange={(e) => updateRow(index, { unit: e.target.value })}
                data-testid={`ingredient-unit-${index}`}
              >
                <option value="">unit</option>
                {UNITS.map((unit) => (
                  <option key={unit} value={unit}>
                    {unit}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
        <button
          type="button"
          className="mt-2 text-sm underline"
          onClick={() => setRows((current) => [...current, { ...EMPTY_ROW }])}
          data-testid="add-ingredient"
        >
          Add ingredient
        </button>
      </fieldset>

      {error ? (
        <p className="text-sm text-red-600" data-testid="form-error">
          {error}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={saving}
        className="rounded bg-black px-4 py-2 text-sm text-white disabled:opacity-50 dark:bg-white dark:text-black"
        data-testid="submit-product"
      >
        {saving ? "Saving…" : "Create product"}
      </button>
    </form>
  );
}
