import Link from "next/link";
import { getAlerts, listDocuments, listProducts, type Product } from "@/lib/api";
import AlertsBanner from "./AlertsBanner";

export const dynamic = "force-dynamic";

async function loadAll(): Promise<{ products: Product[]; docs: Awaited<ReturnType<typeof listDocuments>>["documents"]; error: string | null }> {
  try {
    const [{ products }, { documents }] = await Promise.all([listProducts(), listDocuments()]);
    return { products, docs: documents, error: null };
  } catch {
    // An unreachable API and an empty account must never look the same.
    return { products: [], docs: [], error: "Could not reach the API." };
  }
}

export default async function Home() {
  const { products, docs, error } = await loadAll();

  return (
    <main className="mx-auto max-w-5xl p-10" data-testid="home">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Compliance twins</h1>
          <p className="mt-1 text-sm opacity-70">
            Describe a product once. See where it fails, in which market, against which clause.
          </p>
        </div>
        <Link
          href="/products/new"
          className="rounded-full bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white"
          data-testid="new-product-link"
        >
          New product
        </Link>
      </header>

      <AlertsBanner />

      {error ? (
        <p className="mt-10 text-sm" style={{ color: "var(--danger)" }} data-testid="products-error">
          {error}
        </p>
      ) : null}

      <section className="mt-8">
        {products.length === 0 && !error ? (
          <div className="card p-8 text-center" data-testid="products-empty">
            <p className="text-sm opacity-70">No products yet.</p>
            <Link href="/products/new" className="mt-3 inline-block text-sm underline">
              Create your compliance twin
            </Link>
          </div>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {products.map((product) => (
              <li key={product.id} className="card p-4" data-testid={`product-${product.id}`}>
                <Link href={`/products/${product.id}`} className="font-medium underline-offset-2 hover:underline">
                  {product.name}
                </Link>
                <div className="mt-1 text-sm opacity-70">
                  {product.product_type.replaceAll("_", " ")} · {product.ingredients.length} ingredients
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {docs.length > 0 ? (
        <section className="mt-10">
          <h2 className="text-sm font-medium uppercase tracking-wide opacity-60">Ingested sources</h2>
          <ul className="mt-3 grid gap-2">
            {docs.slice(0, 5).map((doc) => (
              <li key={doc.id}>
                <Link
                  href={`/documents/${doc.id}`}
                  className="card block p-3 text-sm hover:border-[var(--accent)]"
                >
                  {doc.filename} · {doc.jurisdiction}
                  <span className="ml-2 opacity-50">{doc.status}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </main>
  );
}
