import Link from "next/link";
import { notFound } from "next/navigation";
import { getProduct } from "@/lib/api";
import ProductForm from "../../ProductForm";

export const dynamic = "force-dynamic";

export default async function EditProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let product;
  try {
    product = (await getProduct(id)).product;
  } catch {
    notFound();
  }

  return (
    <main className="mx-auto max-w-3xl px-5 py-8 sm:px-6 sm:py-12" data-testid="edit-product">
      <Link href={`/products/${id}`} className="btn btn-quiet btn-small -ml-2">← Back to the product</Link>
      <h1 className="t-large-title mt-3">Correct this product</h1>
      <p className="t-body t-secondary prose-measure mt-2">
        Change anything that is wrong and save. Every market is checked again straight away, so a
        corrected ingredient can change an answer on the next screen.
      </p>
      <ProductForm product={product} />
    </main>
  );
}
