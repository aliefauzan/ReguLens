"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { deleteProduct } from "@/lib/api";

/**
 * Correct or remove a product.
 *
 * Delete asks in place rather than through a browser dialog: the confirmation
 * can then say what actually goes — the product and every verdict derived from
 * it — which "Are you sure?" cannot.
 */
export default function ProductActions({
  productId,
  productName,
}: {
  productId: string;
  productName: string;
}) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    setError(null);
    setBusy(true);
    try {
      await deleteProduct(productId);
      router.push("/");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The product was not deleted.");
      setBusy(false);
    }
  }

  if (confirming) {
    return (
      <div className="card p-4" data-testid="delete-confirm" style={{ maxWidth: 340 }}>
        <p className="t-subhead" style={{ fontWeight: 600 }}>
          Delete “{productName}”?
        </p>
        <p className="t-footnote t-secondary mt-1">
          The product and every verdict worked out for it go. The rules you added stay. This cannot
          be undone.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            className="btn btn-small"
            onClick={remove}
            disabled={busy}
            style={{ background: "var(--danger)", color: "#fff" }}
            data-testid="delete-confirm-yes"
          >
            {busy ? "Deleting…" : "Yes, delete it"}
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-small"
            onClick={() => setConfirming(false)}
            disabled={busy}
            data-testid="delete-cancel"
          >
            Keep it
          </button>
        </div>
        {error ? (
          <p className="t-footnote mt-2" style={{ color: "var(--danger)" }} data-testid="delete-error">
            {error}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-2">
      <Link
        href={`/products/${productId}/edit`}
        className="btn btn-secondary btn-small"
        data-testid="edit-product"
      >
        Correct this product
      </Link>
      <button
        type="button"
        className="btn btn-quiet btn-small"
        onClick={() => setConfirming(true)}
        data-testid="delete-product"
      >
        Delete
      </button>
    </div>
  );
}
