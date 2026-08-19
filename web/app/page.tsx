import Link from "next/link";
import { listProducts, type Product } from "@/lib/api";

export const dynamic = "force-dynamic";

async function loadProducts(): Promise<{ products: Product[]; error: string | null }> {
  try {
    return { products: (await listProducts()).products, error: null };
  } catch {
    // An unreachable API and an empty account must never look the same.
    return { products: [], error: "Could not reach the API." };
  }
}

export default async function Home() {
  const { products, error } = await loadProducts();

  return (
    <main className="mx-auto max-w-3xl p-10" data-testid="home">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold">ReguLens</h1>
          <p className="mt-1 text-sm opacity-70">
            Describe a product once. See where it fails, in which market, against which clause.
          </p>
        </div>
        <Link
          href="/products/new"
          className="rounded bg-black px-3 py-2 text-sm text-white dark:bg-white dark:text-black"
          data-testid="new-product-link"
        >
          New product
        </Link>
      </header>

      {error ? (
        <p className="mt-10 text-sm text-red-600" data-testid="products-error">
          {error}
        </p>
      ) : products.length === 0 ? (
        <div className="mt-10 rounded border border-dashed p-8 text-center" data-testid="products-empty">
          <p className="text-sm opacity-70">No products yet.</p>
          <Link href="/products/new" className="mt-3 inline-block text-sm underline">
            Create your compliance twin
          </Link>
        </div>
      ) : (
        <ul className="mt-10 space-y-3" data-testid="products-list">
          {products.map((product) => (
            <li key={product.id} className="rounded border p-4" data-testid={`product-${product.id}`}>
              <Link href={`/products/${product.id}`} className="font-medium underline">
                {product.name}
              </Link>
              <div className="mt-1 text-sm opacity-70">
                {product.product_type.replaceAll("_", " ")} · {product.ingredients.length} ingredients
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
