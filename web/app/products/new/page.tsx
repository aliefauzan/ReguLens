import ProductForm from "./form";

export default function NewProductPage() {
  return (
    <main className="mx-auto max-w-3xl p-10" data-testid="new-product">
      <h1 className="text-2xl font-semibold">New product</h1>
      <p className="mt-1 text-sm opacity-70">
        This becomes the compliance twin every later answer reasons against.
      </p>
      <ProductForm />
    </main>
  );
}
