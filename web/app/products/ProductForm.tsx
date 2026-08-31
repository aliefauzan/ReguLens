"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { createProduct, updateProduct, PRODUCT_TYPES, type Product } from "@/lib/api";
import { plain } from "../_ui/status";
import IngredientsField, { type Row } from "./IngredientsField";
import MarketsField from "./MarketsField";

const COUNTRIES = [
  { code: "ID", label: "Indonesia" },
  { code: "DE", label: "Germany" },
  { code: "MY", label: "Malaysia" },
  { code: "SG", label: "Singapore" },
  { code: "TH", label: "Thailand" },
  { code: "VN", label: "Vietnam" },
];

/** An existing product's ingredients, back in the shape the row editor uses. */
function rowsFrom(product: Product): Row[] {
  return product.ingredients.map((ingredient) => ({
    name: ingredient.name,
    amount: ingredient.amount === null ? "" : String(ingredient.amount),
    unit: ingredient.unit ?? "",
  }));
}

/**
 * One form, two jobs: create a product, or correct one.
 *
 * The create form always promised "you can edit any of this later" and there
 * was no way to. A misspelt ingredient matches no clause and the product then
 * reads as having no problems, so being unable to fix a typo was not cosmetic.
 */
export default function ProductForm({ product }: { product?: Product }) {
  const editing = product !== undefined;
  const router = useRouter();
  const [name, setName] = useState(product?.name ?? "Herbal Drink Powder");
  const [productType, setProductType] = useState<string>(product?.product_type ?? PRODUCT_TYPES[0]);
  const [origin, setOrigin] = useState(product?.origin ?? "ID");
  const [packaging, setPackaging] = useState(product?.packaging ?? "250g plastic pouch");
  const [markets, setMarkets] = useState<string[]>(product?.target_markets ?? ["market_de"]);
  const [rows, setRows] = useState<Row[]>(
    product
      ? rowsFrom(product)
      : [
          { name: "ginger", amount: "", unit: "" },
          { name: "sodium benzoate", amount: "0.08", unit: "percent_w_w" },
        ],
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    const numberWithoutUnit = rows.find((row) => row.name.trim() && row.amount.trim() && !row.unit);
    if (numberWithoutUnit) {
      setError(
        `“${numberWithoutUnit.name}” has an amount but no unit. Pick a unit, or clear the amount.`,
      );
      return;
    }

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
      const body = {
        name,
        product_type: productType,
        origin,
        packaging: packaging || null,
        target_markets: markets,
        ingredients,
      };
      const saved = editing ? await updateProduct(product.id, body) : await createProduct(body);
      router.push(`/products/${saved.id}`);
      // The product page is server-rendered, so without this the reader lands
      // on the version they just changed.
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Nothing was saved.");
      setSaving(false);
    }
  }

  return (
    <form className="mt-6 space-y-6" onSubmit={submit} data-testid="product-form">
      <section className="card p-6">
        <h2 className="t-headline">The basics</h2>
        <div className="mt-4 grid gap-5 sm:grid-cols-2">
          <label className="block">
            <span className="label">What is it called?</span>
            <input
              className="field"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              data-testid="field-name"
            />
          </label>

          <label className="block">
            <span className="label">What kind of product is it?</span>
            <select
              className="field"
              value={productType}
              onChange={(e) => setProductType(e.target.value)}
              data-testid="field-product-type"
            >
              {PRODUCT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {plain(type)}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="label">Where is it made?</span>
            <select
              className="field"
              value={origin}
              onChange={(e) => setOrigin(e.target.value)}
              data-testid="field-origin"
            >
              {COUNTRIES.map((country) => (
                <option key={country.code} value={country.code}>
                  {country.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="label">How is it packaged?</span>
            <input
              className="field"
              value={packaging}
              onChange={(e) => setPackaging(e.target.value)}
              placeholder="250g plastic pouch"
              data-testid="field-packaging"
            />
            <span className="help">Optional.</span>
          </label>
        </div>
      </section>

      <MarketsField value={markets} onChange={setMarkets} />

      <IngredientsField rows={rows} setRows={setRows} initialMode={editing ? "list" : "paste"} />

      {error ? (
        <div className="card p-5" data-testid="form-error">
          <p className="t-headline" style={{ color: "var(--danger)" }}>That did not save</p>
          <p className="t-subhead t-secondary mt-1">{error}</p>
        </div>
      ) : null}

      <div className="flex items-center gap-3">
        <button type="submit" disabled={saving} className="btn btn-primary" data-testid="submit-product">
          {saving ? "Saving…" : editing ? "Save changes" : "Save product"}
        </button>
        {editing ? (
          <Link href={`/products/${product.id}`} className="btn btn-quiet btn-small">
            Cancel
          </Link>
        ) : (
          <span className="t-footnote t-secondary">You can edit any of this later.</span>
        )}
      </div>
    </form>
  );
}
