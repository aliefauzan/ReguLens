import Link from "next/link";
import ProductForm from "./form";

export default function NewProductPage() {
  return (
    <main className="mx-auto max-w-3xl px-5 py-8 sm:px-6 sm:py-12" data-testid="new-product">
      <Link href="/" className="btn btn-quiet btn-small -ml-2">← Back</Link>
      <h1 className="t-large-title mt-3">Add a product</h1>
      <p className="t-subhead t-secondary mt-2">
        Tell us what it is and what is inside it. Every answer ReguLens gives later is measured
        against what you enter here, so an amount you are unsure of is better left blank than guessed.
      </p>
      <ProductForm />
    </main>
  );
}
